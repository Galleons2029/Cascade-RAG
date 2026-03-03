from collections import defaultdict
from datetime import datetime, timedelta
import importlib
import json
import logging
import os
from pathlib import Path
import re
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, TypedDict

import pandas as pd
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, InterruptOnConfig, TodoListMiddleware
from langchain.agents.middleware.summarization import SummarizationMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.engine.create import create_engine
from sqlalchemy.pool.impl import QueuePool

from app.configs import postgres_config

load_dotenv()
api_key = os.getenv("SILICON_API_KEY")
base_url = os.getenv("SILICON_BASE_URL")
model_name = os.getenv("LLM_MODEL")

pg_host = postgres_config.PG_HOST
pg_port = postgres_config.PG_PORT
pg_user = postgres_config.PG_USER
pg_password = postgres_config.PG_PASSWORD
pg_db = postgres_config.PG_DB

db_uri = f"postgresql+psycopg://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"
model = ChatOpenAI(
    model=model_name,
    temperature=0.2,
    api_key=api_key,
    base_url=base_url,
)

logging.basicConfig(level=logging.DEBUG)

engine = create_engine(
    db_uri,
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False
)

DATE_FMT = "%Y%m%d"
START_DT = "20250601"
END_DT = "20250610"
TYPE_NAMES = ("type1", "type2", "type3")


class PandasSQLQueryTool:
    def __init__(self, engine):
        self.engine = engine

    def invoke(self, query: str, params: Optional[Dict] = None) -> List[Dict[str, Any]]:
        try:
            with self.engine.connect() as conn:
                result = pd.read_sql(query, conn, params=params)
                return result.to_dict("records")
        except Exception as exc:
            logging.error("查询执行失败: %s", exc)
            logging.error("SQL: %s", query)
            return []


execute_query_tool = PandasSQLQueryTool(engine)


def _sanitize_mermaid_code(raw: str) -> str:
    if not raw:
        return ""
    code = str(raw).strip()
    fenced = re.search(r"```(?:mermaid)?\s*([\s\S]*?)```", code, flags=re.IGNORECASE)
    if fenced:
        code = fenced.group(1).strip()
    code = re.sub(r"^mermaid\s*", "", code, flags=re.IGNORECASE).strip()
    code = re.sub(r"^`+", "", code).strip()
    if not re.match(r"^(graph|flowchart)\s", code, flags=re.IGNORECASE):
        code = "graph TD\n" + code
    return code


def summarize_result_for_mermaid(result: Dict[str, Any]) -> str:
    text = {
        "account_key": {
            "org_num": result.get("org_num", ""),
            "sbj_num": result.get("sbj_num", ""),
            "ccy": result.get("ccy", ""),
            "acg_dt": result.get("acg_dt", ""),
        },
        "type": result.get("type", "unknown"),
        "history_total_diff": result.get("history_total_diff", 0),
        "individual_total_diff": result.get("individual_total_diff", 0),
        "account_inconsistent_count": result.get("account_inconsistent_count", 0),
        "inconsistent_accounts_example": result.get("inconsistent_accounts", [])[:5],
        "change_dates": result.get("change_dates", []),
        "change_list": result.get("change_list", []),
        "zero_span": result.get("zero_span", {}),
    }
    return json.dumps(text, ensure_ascii=False, indent=2)


def call_llm_api_for_mermaid(analysis_json: str) -> str:
    system_prompt = """
你是一个会画流程图的财务分析专家。用户会给你一段 JSON，里面包含账户总分不平的分析结果。
你的任务：
- 根据 JSON 信息，用清晰中文步骤生成一段 mermaid 流程图（graph TD）。
- 风格必须严格模仿下方示例。

示例：
```mermaid
graph TD
  A[总账余额≠分户账合计] --> B{差异类型判断}
  B -->|时间性| C[检查T+1跑批状态]
  B -->|永久性| D[逐笔核对分户账]
  C --> E[重跑当日批处理]
  D --> F[定位错账/折算错误]
  E --> G[差异消除]
  F --> G
```
"""
    user_prompt = (
        "下面是一个账户总分不平分析结果，请你根据其中的信息画一段 mermaid 流程图：\n\n"
        f"{analysis_json}\n\n"
        "请直接给出 mermaid 代码块。"
    )
    response = model.invoke(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
    )
    content = response.content if hasattr(response, "content") else str(response)
    return content.strip()


def _build_default_plan_steps(org: str, sbj: str, ccy: str, dt: str) -> List[str]:
    return [
        f"确认 {dt} 总分差额是否与 tot 表一致 ({org}/{sbj}/{ccy})",
        "核对当日传票借贷发生额与余额变动",
        "抽取分户余额前后两日差异，验证平衡公式",
        "检查红蓝字冲销凭证导致的差额跳变",
        "输出可疑账号清单并安排复核",
    ]


def generate_plan_steps_for_target(record: Dict[str, Any], plan_prompt: str = "") -> List[Dict[str, str]]:
    org = record.get("org_num", "")
    sbj = record.get("sbj_num", "")
    ccy = record.get("ccy", "")
    dt = record.get("dt", "")
    if not plan_prompt:
        return [{"description": s, "status": "enabled"} for s in _build_default_plan_steps(org, sbj, ccy, dt)]

    system_prompt = (
        "你是一名资深财务核对专家，专长是处理总分不平。\n"
        "请基于给定的机构/科目/币种/账期，输出 5-8 条可执行的待办事项。\n"
        "要求：\n"
        "- 每条是可执行的行动句，中文，尽量简短\n"
        "- 关注核对、复核、风险排查、流程触发等动作\n"
        "- 不要返回其他解释性文字，优先 JSON 或纯列表"
    )
    steps: List[str] = []
    try:
        resp = model.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"业务参数：机构 {org} 科目 {sbj} 币种 {ccy} 日期 {dt}。\n{plan_prompt}"),
            ]
        )
        content = resp.content if hasattr(resp, "content") else str(resp)
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "steps" in parsed:
                steps = parsed.get("steps", [])
            elif isinstance(parsed, list):
                steps = parsed
        except Exception:
            steps = [line.strip() for line in str(content).splitlines() if line.strip()]
    except Exception as exc:
        logging.error("生成计划步骤失败，使用默认步骤: %s", exc)

    cleaned: List[Dict[str, str]] = []
    for raw in steps:
        text = str(raw).strip()
        text = re.sub(r"^[\-\d\.\s•①-⑩一二三四五六七八九十]+", "", text)
        if text:
            cleaned.append({"description": text, "status": "enabled"})

    if not cleaned:
        cleaned = [{"description": s, "status": "enabled"} for s in _build_default_plan_steps(org, sbj, ccy, dt)]

    return cleaned[:12]


def load_ccy_mapping() -> Dict[str, str]:
    sql = "SELECT ccy_int, ccy_symb FROM ccy_mapping"
    results = execute_query_tool.invoke(sql)
    return {row["ccy_symb"]: row["ccy_int"] for row in results}


def normalize_dt_value(dt: str) -> str:
    if not dt:
        return ""
    raw = str(dt).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime(DATE_FMT)
        except ValueError:
            continue
    return raw


def parse_dt(dt: str) -> datetime:
    normalized = normalize_dt_value(dt)
    return datetime.strptime(normalized, DATE_FMT)


def classify_errors(records: List[Dict[str, Any]]) -> Dict[str, List[Any]]:
    date_set = set()
    dt_start = parse_dt(START_DT)
    dt_end = parse_dt(END_DT)
    for d in range((dt_end - dt_start).days + 1):
        date_set.add((dt_start + timedelta(days=d)).strftime(DATE_FMT))

    bucket = defaultdict(list)
    for r in records:
        key = (r["org_num"], r["sbj_num"], r["ccy"])
        bucket[key].append(r)

    type1, type2, type3 = [], [], []
    for rows in bucket.values():
        rows.sort(key=lambda x: x["dt"])
        exist_dates = {r["dt"] for r in rows}
        full_period = (exist_dates == date_set)
        diffs = [float(r["tot_mint_dif"]) for r in rows]
        non_zero_count = sum(1 for d in diffs if d != 0)

        if full_period and len(set(diffs)) == 1:
            rows[0]["is_first"] = True
            type1.append(rows[0])
            continue

        if not full_period and 0 < non_zero_count < len(diffs):
            first_nz = next(i for i, d in enumerate(diffs) if d != 0)
            last_nz = len(diffs) - 1 - next(i for i, d in enumerate(reversed(diffs)) if d != 0)
            rows[0]["zero_span"] = {"start": rows[first_nz]["dt"], "end": rows[last_nz]["dt"]}
            type3.append(rows[0])
            continue

        change_list, change_dates = [], []
        for i, d in enumerate(diffs):
            if i == 0 or d != diffs[i - 1]:
                change_list.append(d)
                change_dates.append(rows[i]["dt"])
        if len(change_list) >= 2:
            rows[0]["change_list"] = change_list
            rows[0]["change_dates"] = change_dates
            type2.append(rows[0])

    return {"type1": type1, "type2": type2, "type3": type3}


def _fetch_tot_records_for_target(org: str, sbj: str, ccy: str) -> List[Dict[str, Any]]:
    sql = f"""
        SELECT org_num, sbj_num, ccy, dt, CAST(NULLIF(tot_mint_dif, '') AS DECIMAL(18,2)) AS tot_mint_dif
        FROM tot
        WHERE org_num = '{org}'
          AND sbj_num = '{sbj}'
          AND ccy = '{ccy}'
          AND dt BETWEEN '{START_DT}' AND '{END_DT}'
        ORDER BY dt;
    """
    rows = execute_query_tool.invoke(sql)
    records: List[Dict[str, Any]] = []
    for r in rows:
        if r.get("tot_mint_dif") is None:
            continue
        records.append(
            {
                "org_num": r.get("org_num"),
                "sbj_num": r.get("sbj_num"),
                "ccy": r.get("ccy"),
                "dt": r.get("dt"),
                "tot_mint_dif": float(r.get("tot_mint_dif")),
            }
        )
    return records


def _classify_single_record(record: Dict[str, Any]) -> Tuple[Dict[str, Any], str, Dict[str, List[Dict[str, Any]]]]:
    org = record.get("org_num", "")
    sbj = record.get("sbj_num", "")
    ccy = record.get("ccy", "")
    records = _fetch_tot_records_for_target(org, sbj, ccy)
    classes = {"type1": [], "type2": [], "type3": []}
    if records:
        classes = classify_errors(records)
    record_type = "type1"
    enriched = dict(record)
    for t in TYPE_NAMES:
        for item in classes.get(t, []):
            if item.get("org_num") == org and item.get("sbj_num") == sbj and item.get("ccy") == ccy:
                enriched.update(item)
                record_type = t
                return enriched, record_type, classes
    return enriched, record_type, classes


class OutputState(TypedDict):
    discrepancies: List[Dict[str, Any]]
    classes: Dict[str, List[Dict[str, Any]]]
    results: List[Dict[str, Any]]
    summary: Dict[str, Any]
    plan_steps: List[Dict[str, str]]
    user_selected_steps: List[str]
    log_lines: List[str]
    sql_query: Optional[str]
    sql_result: Optional[str]
    sql_messages: Optional[List[str]]


class AgentState(TypedDict, total=False):
    discrepancies: List[Dict[str, Any]]
    classes: Dict[str, List[Dict[str, Any]]]
    current_record: Dict[str, Any]
    current_target: Tuple[str, str, str, str]
    current_type: str
    history: Dict[str, Any]
    individual: Dict[str, Any]
    per_account: List[Dict[str, Any]]
    results: List[Dict[str, Any]]
    summary: Dict[str, Any]
    target_org: str
    target_sbj: str
    target_ccy: str
    target_dt: str
    skip_validation: bool
    plan_steps: List[Dict[str, str]]
    plan_prompt: str
    user_selected_steps: List[str]
    log_lines: List[str]


def build_classification_lines_cn(
    record: Dict[str, Any],
    record_type: str,
    classes: Dict[str, List[Dict[str, Any]]],
    discrepancies: List[Dict[str, Any]],
) -> List[str]:
    total_records = len(discrepancies) if discrepancies else 1
    type1_records = classes.get("type1", [])
    type2_records = classes.get("type2", [])
    type3_records = classes.get("type3", [])
    lines = ["【错误分类分析报告】"]
    lines.append(f"总计发现 {total_records} 条不平记录，分类如下：")
    lines.append(f"  - Type1 (恒定差额): {len(type1_records)} 组")
    lines.append(f"  - Type2 (差额变化): {len(type2_records)} 组")
    lines.append(f"  - Type3 (差额归零): {len(type3_records)} 组")

    if record_type == "type1":
        lines.append("【Type1 - 恒定差额错误】")
        lines.append("分析原因：6月1日起总账户与分户合计差额恒定，业务期间分户/总账同步变动。该总分不平发生在6月1日之前，建议您往6月1日前追溯原因。")
        lines.append("判断标准：")
        lines.append("  1. 该组(org_num, sbj_num, ccy)在查询期间内所有日期都有记录")
        lines.append("  2. 所有日期的 tot_mint_dif 值完全相同（恒定差额）")
        lines.append("  3. 说明：可能存在系统性的余额计算错误或初始余额设置问题")
        lines.append(
            "详情：机构 {org}, 科目 {sbj}, 币种 {ccy}, 差额 {dif}".format(
                org=record.get("org_num"),
                sbj=record.get("sbj_num"),
                ccy=record.get("ccy"),
                dif=record.get("tot_mint_dif", "N/A"),
            )
        )
    elif record_type == "type2":
        lines.append("【Type2 - 差额变化错误】")
        lines.append("分析原因：6月1日起总账户与分户合计产生差额不固定，业务期间分户/总账不同步变动。该总分不平发生在6月1日之前，同时中间又发生了新的错误，建议您对该账户的相关情况进行具体分析。")
        lines.append("判断标准：")
        lines.append("  1. 在查询期间内，该组的 tot_mint_dif 值发生了至少一次变化")
        lines.append("  2. 存在多个不同的差额值（change_list 长度 ≥ 2）")
        lines.append("  3. 说明：可能在特定日期发生了交易或调整，导致差额发生变化")
        if record.get("change_list"):
            lines.append(f"  变化点: {len(record.get('change_list', []))} 个，差额值: {record.get('change_list')}")
        if record.get("change_dates"):
            lines.append(f"  变化日期: {record.get('change_dates')}")
    elif record_type == "type3":
        lines.append("【Type3 - 差额归零错误】")
        lines.append("分析原因：账户部分天数总分平衡，部分天数总分不平。建议借助平衡法则“当天余额=上一天余额±借方发生额±贷方发生额”进行计算找到错误")
        lines.append("判断标准：")
        lines.append("  1. 该组在查询期间内不是所有日期都有记录（非全量）")
        lines.append("  2. 不平记录数少于总天数，但大于0")
        lines.append("  3. 存在一个日期范围（zero_span），在这个范围内差额从非零变为零")
        lines.append("  4. 说明：可能在某段时间内发生了错误，之后被纠正或自动归零")
        if record.get("zero_span"):
            zero_span = record.get("zero_span", {})
            lines.append(f"  异常日期范围: {zero_span.get('start')} 至 {zero_span.get('end')}")
    lines.append("开始逐组验证...")
    return lines


def _validate_voucher_today(acg_dt: str, org_num: str, sbj_num: str, ccy_symb: str) -> Dict[str, Any]:
    sql = f"""
        SELECT
            t.acct_num,
            t.acg_org_num,
            t.sbj_num,
            t.ccy_symb,
            SUM(CASE
                    WHEN t.ldin_flg = 'D' AND (t.rd_flg IS NULL OR t.rd_flg = 'B') THEN CAST(t.amt AS DECIMAL(18,2))
                    WHEN t.ldin_flg = 'D' AND t.rd_flg = 'R' THEN -CAST(t.amt AS DECIMAL(18,2))
                    ELSE 0
                END) AS debit_amt,
            SUM(CASE
                    WHEN t.ldin_flg = 'C' AND (t.rd_flg IS NULL OR t.rd_flg = 'B') THEN CAST(t.amt AS DECIMAL(18,2))
                    WHEN t.ldin_flg = 'C' AND t.rd_flg = 'R' THEN -CAST(t.amt AS DECIMAL(18,2))
                    ELSE 0
                END) AS credit_amt,
            SUM(CASE
                    WHEN t.ldin_flg = 'D' AND (t.rd_flg IS NULL OR t.rd_flg = 'B') THEN CAST(t.amt AS DECIMAL(18,2))
                    WHEN t.ldin_flg = 'D' AND t.rd_flg = 'R' THEN -CAST(t.amt AS DECIMAL(18,2))
                    WHEN t.ldin_flg = 'C' AND (t.rd_flg IS NULL OR t.rd_flg = 'B') THEN -CAST(t.amt AS DECIMAL(18,2))
                    WHEN t.ldin_flg = 'C' AND t.rd_flg = 'R' THEN CAST(t.amt AS DECIMAL(18,2))
                    ELSE 0
                END) AS balance_diff
        FROM history t
        WHERE t.dt = '{acg_dt}'
          AND t.acg_org_num = '{org_num}'
          AND t.sbj_num = '{sbj_num}'
          AND t.ccy_symb = '{ccy_symb}'
        GROUP BY t.acct_num, t.acg_org_num, t.sbj_num, t.ccy_symb;
    """
    rows = execute_query_tool.invoke(sql)
    return {
        "count": len(rows),
        "total_debit": sum(r["debit_amt"] for r in rows),
        "total_credit": sum(r["credit_amt"] for r in rows),
        "total_diff": sum(r["balance_diff"] for r in rows),
        "records": rows,
        "summary_diff": sum(r["debit_amt"] for r in rows) - sum(r["credit_amt"] for r in rows),
    }


def _validate_ledger_day(acg_dt: str, org_num: str, sbj_num: str, ccy_int: str) -> Dict[str, Any]:
    acg_dt_norm = normalize_dt_value(acg_dt)
    acg_dt_after = (datetime.strptime(acg_dt_norm, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
    sql = f"""
        SELECT 
            a.acct_num,
            a.sbj_num,
            a.ccy,
            a.bal_prev_day,
            b.bal_curr_day,
            b.bal_curr_day - a.bal_prev_day AS balance_diff
        FROM (
            SELECT acct_num, sbj_num, ccy, CAST(sbact_acct_bal AS DECIMAL(18,2)) AS bal_prev_day
            FROM individual
            WHERE dt = '{acg_dt_norm}' 
              AND org_num = '{org_num}'
              AND sbj_num = '{sbj_num}'
              AND ccy = '{ccy_int}'
        ) a
        JOIN (
            SELECT acct_num, sbj_num, ccy, CAST(sbact_acct_bal AS DECIMAL(18,2)) AS bal_curr_day
            FROM individual
            WHERE dt = '{acg_dt_after}' 
              AND org_num = '{org_num}'
              AND sbj_num = '{sbj_num}'
              AND ccy = '{ccy_int}'
        ) b ON a.acct_num = b.acct_num 
           AND a.sbj_num = b.sbj_num 
           AND a.ccy = b.ccy;
    """
    rows = execute_query_tool.invoke(sql)
    return {
        "count": len(rows),
        "records": rows,
        "total_diff": sum(r["balance_diff"] for r in rows),
    }


def _compare_account_diffs(history_rows: List[Dict[str, Any]], individual_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    history = {r["acct_num"]: float(r["balance_diff"]) for r in history_rows}
    individual = {r["acct_num"]: float(r["balance_diff"]) for r in individual_rows}
    common = sorted(set(history) & set(individual))
    out = []
    for acct in common:
        h = abs(history[acct])
        i = abs(individual[acct])
        diff = h - i
        out.append(
            {
                "acct_num": acct,
                "history_balance_diff": h,
                "individual_balance_diff": i,
                "difference": diff,
                "is_consistent": abs(diff) < 0.01,
                "error_rate": abs(diff / h * 100) if h != 0 else 0,
            }
        )
    return out


def build_account_result_lines_cn(state: AgentState, result: Dict[str, Any], per: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    org, sbj, ccy, acg_dt = result.get("org_num"), result.get("sbj_num"), result.get("ccy"), result.get("acg_dt")
    rtype = result.get("type", "unknown")
    lines.append(f"【处理完成 - {rtype.upper()}】")
    lines.append(f"机构: {org}, 科目: {sbj}, 币种: {ccy}, 日期: {acg_dt}")

    record = state.get("current_record", {})
    if rtype == "type1":
        lines.append("【错误原因分析】")
        lines.append("Type1 - 恒定差额错误：")
        lines.append("  6月1日起总账户与分户合计差额恒定，业务期间分户/总账同步变动。")
        lines.append("  可能原因：")
        lines.append("    1. 系统性的余额计算错误")
        lines.append("    2. 初始余额设置问题")
        lines.append("    3. 科目余额与分户余额之间存在固定偏差")
        lines.append(f"  恒定差额值: {record.get('tot_mint_dif', 'N/A')}")
    elif rtype == "type2":
        lines.append("【错误原因分析】")
        lines.append("Type2 - 差额变化错误：")
        lines.append("  6月1日起总账户与分户合计产生差额不固定，业务期间分户/总账不同步变动。")
        lines.append("  可能原因：")
        lines.append("    1. 在特定日期发生了交易或调整")
        lines.append("    2. 传票数据与分户余额数据在变化点日期不一致")
        lines.append("    3. 可能存在数据录入错误或冲正操作")
        if record.get("change_list"):
            lines.append(f"  差额变化序列: {record.get('change_list')}")
        if record.get("change_dates"):
            lines.append(f"  变化日期: {record.get('change_dates')}")
    elif rtype == "type3":
        lines.append("【错误原因分析】")
        lines.append("Type3 - 差额归零错误：")
        lines.append("  账户部分天数总分平衡，部分天数总分不平。")
        lines.append("  可能原因：")
        lines.append("    1. 在某段时间内发生了错误，之后被纠正")
        lines.append("    2. 可能存在红蓝字冲销操作")
        lines.append("    3. 数据在异常期间后自动归零")
        zero_span = record.get("zero_span", {})
        if zero_span:
            lines.append(f"  异常日期范围: {zero_span.get('start')} 至 {zero_span.get('end')}")

    lines.append("【验证结果汇总】")
    hist = state.get("history", {})
    indiv = state.get("individual", {})
    lines.append("  History表(传票发生额):")
    lines.append(f"    - 账户数: {hist.get('count', 0)}")
    lines.append(f"    - 总借方: {float(hist.get('total_debit', 0) or 0):.2f}")
    lines.append(f"    - 总贷方: {float(hist.get('total_credit', 0) or 0):.2f}")
    lines.append(f"    - 总差额: {float(hist.get('total_diff', 0) or 0):.2f}")
    lines.append("  Individual表(分户余额差):")
    lines.append(f"    - 账户数: {indiv.get('count', 0)}")
    lines.append(f"    - 总差额: {float(indiv.get('total_diff', 0) or 0):.2f}")
    lines.append(f"  不一致账户数: {result.get('account_inconsistent_count', 0)}")

    if per:
        lines.append("【可疑账号列表（前10条）】")
        for idx, item in enumerate(per[:10], 1):
            lines.append(
                "    [{idx}] 账号: {acct}, 差异: {diff:.4f}, 错误率: {err:.6f}%".format(
                    idx=idx,
                    acct=item.get("acct_num", "?"),
                    diff=float(item.get("difference", 0) or 0),
                    err=float(item.get("error_rate", 0) or 0),
                )
            )
    else:
        lines.append("未发现可疑账号。")

    return lines


def build_progress_steps_cn(result: Dict[str, Any]) -> List[Dict[str, str]]:
    steps: List[Dict[str, str]] = [
        {"description": "加载账期数据并校验币种映射", "status": "completed"},
        {"description": "分类差异模式 (type1/type2/type3)", "status": "completed"},
        {"description": "比对传票与分户差额，提取可疑账号", "status": "completed"},
        {"description": "生成处理流程图与摘要", "status": "completed"},
        {"description": "等待人工复核与派单", "status": "pending"},
    ]
    t = result.get("type")
    if t == "type2":
        steps[1]["description"] = "识别差额变化序列 (type2)"
    elif t == "type3":
        steps[1]["description"] = "识别归零区间 (type3)"
    return steps


def node_scan(state: AgentState) -> AgentState:
    target_org = state.get("target_org")
    target_sbj = state.get("target_sbj")
    target_ccy = state.get("target_ccy")
    target_dt = normalize_dt_value(state.get("target_dt", "") or "")

    if not all([target_org, target_sbj, target_ccy, target_dt]):
        state["discrepancies"] = []
        state["classes"] = {"type1": [], "type2": [], "type3": []}
        state["skip_validation"] = True
        state["current_target"] = ("", "", "", "")
        state["plan_steps"] = []
        state["results"] = []
        state["log_lines"] = ["缺少必要参数，跳过核对。"]
        return state

    base_record = {
        "org_num": target_org,
        "sbj_num": target_sbj,
        "ccy": target_ccy,
        "dt": target_dt,
    }

    enriched, record_type, classes = _classify_single_record(base_record)
    discrepancies = _fetch_tot_records_for_target(target_org, target_sbj, target_ccy) or [base_record]

    state["discrepancies"] = discrepancies
    state["classes"] = classes
    state["current_record"] = enriched
    state["current_target"] = (target_org, target_sbj, target_ccy, target_dt)
    state["current_type"] = record_type
    state["skip_validation"] = False

    try:
        plan_prompt = state.get("plan_prompt", "") or ""
        state["plan_steps"] = generate_plan_steps_for_target(enriched, plan_prompt)
    except Exception as exc:
        logging.error("生成计划步骤失败，使用默认步骤: %s", exc)
        state["plan_steps"] = [
            {"description": s, "status": "enabled"}
            for s in _build_default_plan_steps(target_org, target_sbj, target_ccy, target_dt)
        ]
    state["user_selected_steps"] = state.get("user_selected_steps", [])
    state["results"] = []

    state["log_lines"] = build_classification_lines_cn(enriched, record_type, classes, discrepancies)
    return state


def node_validate(state: AgentState) -> AgentState:
    if state.get("skip_validation"):
        return state
    org, sbj, ccy_symb, acg_dt = state["current_target"]

    ccy_symb_norm = (ccy_symb or "").strip().upper()
    if not acg_dt:
        logging.warning("缺少账期，跳过校验")
        state["skip_validation"] = True
        return state

    ccy_mapping = load_ccy_mapping()
    ccy_int = ccy_mapping.get(ccy_symb_norm, ccy_symb_norm)

    try:
        history = _validate_voucher_today(acg_dt, org, sbj, ccy_symb_norm)
    except Exception as exc:
        logging.warning("history 校验失败，跳过: %s", exc)
        history = {"count": 0, "total_debit": 0, "total_credit": 0, "total_diff": 0, "records": [], "summary_diff": 0}
    try:
        individual = _validate_ledger_day(acg_dt, org, sbj, ccy_int)
    except Exception as exc:
        logging.warning("ledger 校验失败，跳过: %s", exc)
        individual = {"count": 0, "records": [], "total_diff": 0}

    state["history"] = history
    state["individual"] = individual
    return state


def node_compare(state: AgentState) -> AgentState:
    if state.get("skip_validation"):
        return state
    per = _compare_account_diffs(state["history"]["records"], state["individual"]["records"])
    state["per_account"] = per
    inc = [r for r in per if not r["is_consistent"]]
    org, sbj, ccy, acg_dt = state["current_target"]

    result = {
        "org_num": org,
        "sbj_num": sbj,
        "ccy": ccy,
        "acg_dt": acg_dt,
        "type": state.get("current_type", "type1"),
        "history_total_diff": state["history"]["total_diff"],
        "individual_total_diff": state["individual"]["total_diff"],
        "account_inconsistent_count": len(inc),
        "inconsistent_accounts": inc[:50],
    }
    result["plan_steps"] = state.get("plan_steps", [])
    if state.get("user_selected_steps"):
        result["user_selected_steps"] = state.get("user_selected_steps", [])

    record = state.get("current_record", {})
    if state.get("current_type") == "type2":
        result["change_list"] = record.get("change_list", [])
        result["change_dates"] = record.get("change_dates", [])
    elif state.get("current_type") == "type3":
        result["zero_span"] = record.get("zero_span", {})

    try:
        analysis_json = summarize_result_for_mermaid(result)
        mermaid_code = call_llm_api_for_mermaid(analysis_json)
        result["mermaid"] = _sanitize_mermaid_code(mermaid_code)
    except Exception as exc:
        logging.error("生成 mermaid 失败: %s", exc)
        result["mermaid"] = _sanitize_mermaid_code(
            """
            ```mermaid
            graph TD
              A[总账余额≠分户账合计] --> B[生成流程图失败，请人工查看日志]
            ```
            """
        )

    result["progress_steps"] = build_progress_steps_cn(result)
    base_lines = state.get("log_lines", [])
    result["log_lines"] = base_lines + build_account_result_lines_cn(state, result, per)
    state["log_lines"] = result["log_lines"]
    state["results"].append(result)

    return state


def node_finish(state: AgentState) -> AgentState:
    total_discrepancies = len(state.get("discrepancies", []))
    state["summary"] = {
        "total_discrepancies": total_discrepancies,
        "group_count": len(state.get("results", [])),
        "type1": len(state.get("classes", {}).get("type1", [])),
        "type2": len(state.get("classes", {}).get("type2", [])),
        "type3": len(state.get("classes", {}).get("type3", [])),
    }
    return state


BASE_AGENT_PROMPT = (
    "In order to complete the objective that the user asks of you, "
    "you have access to a number of standard tools."
)

REACT_BANK_SYSTEM_PROMPT = """You are a bank reconciliation analysis agent.
Workflow:
1) If the user provides org/sbj/ccy/dt, call analyze_react_bank exactly once (include plan_prompt/user_selected_steps when provided).
2) If the user asks for SQL generation, call the SQL graph and return SQL + result.
3) If any parameter is missing, ask a concise follow-up.
4) After the tool returns, respond with only the tool result JSON.
Stopping criteria: after returning the tool output."""


def _run_pipeline(initial_state: AgentState) -> AgentState:
    state: AgentState = dict(initial_state)
    state = node_scan(state)
    if state.get("skip_validation"):
        return node_finish(state)
    state = node_validate(state)
    state = node_compare(state)
    return node_finish(state)


def _build_output(state: AgentState) -> OutputState:
    return {
        "discrepancies": state.get("discrepancies", []),
        "classes": state.get("classes", {}),
        "results": state.get("results", []),
        "summary": state.get("summary", {}),
        "plan_steps": state.get("plan_steps", []),
        "user_selected_steps": state.get("user_selected_steps", []),
        "log_lines": state.get("log_lines", []),
        "sql_query": None,
        "sql_result": None,
        "sql_messages": None,
    }


@tool(parse_docstring=True)
def analyze_react_bank(
    org_num: str,
    sbj_num: str,
    ccy: str,
    dt: str,
    plan_prompt: str = "",
    user_selected_steps: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run the bank reconciliation pipeline and return structured results.

    Args:
        org_num: Organization number.
        sbj_num: Subject/account number.
        ccy: Currency code.
        dt: Target date (YYYY-MM-DD).
        plan_prompt: Optional plan guidance.
        user_selected_steps: Optional list of step identifiers selected by user.

    Returns:
        Structured reconciliation results for the requested parameters.
    """
    initial: AgentState = {
        "target_org": org_num,
        "target_sbj": sbj_num,
        "target_ccy": ccy,
        "target_dt": normalize_dt_value(dt),
        "plan_prompt": plan_prompt or "",
        "user_selected_steps": user_selected_steps or [],
    }
    final_state = _run_pipeline(initial)
    return _build_output(final_state)


def _extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    raw = text.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, flags=re.IGNORECASE)
    candidate = (fenced.group(1) if fenced else raw).strip()
    if not candidate.startswith("{"):
        match = re.search(r"(\{[\s\S]*\})", candidate)
        candidate = match.group(1).strip() if match else ""
    if not candidate:
        return None
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _extract_input_payload(raw_state: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    if not raw_state:
        return payload

    def _set_if(key: str, value: Any) -> None:
        if value is not None and value != "":
            payload[key] = value

    _set_if("org", raw_state.get("target_org"))
    _set_if("sbj", raw_state.get("target_sbj"))
    _set_if("ccy", raw_state.get("target_ccy"))
    _set_if("dt", raw_state.get("target_dt"))
    _set_if("plan_prompt", raw_state.get("plan_prompt"))
    _set_if("user_selected_steps", raw_state.get("user_selected_steps"))

    _set_if("org", raw_state.get("org"))
    _set_if("sbj", raw_state.get("sbj"))
    _set_if("ccy", raw_state.get("ccy"))
    _set_if("dt", raw_state.get("dt"))
    _set_if("plan_prompt", raw_state.get("planPrompt"))
    _set_if("user_selected_steps", raw_state.get("selectedSteps"))
    _set_if("mode", raw_state.get("mode"))
    _set_if("sql_request", raw_state.get("sql_request"))
    _set_if("sql_request", raw_state.get("sqlRequest"))
    _set_if("sql_request", raw_state.get("sql_question"))
    _set_if("sql_request", raw_state.get("query"))

    messages = raw_state.get("messages")
    if isinstance(messages, list) and messages:
        last = messages[-1]
        content = last.get("content") if isinstance(last, dict) else getattr(last, "content", None)
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(str(item.get("text", "")))
            text = "".join(parts)
        parsed = _extract_json_from_text(text)
        if parsed:
            _set_if("org", parsed.get("org") or parsed.get("org_num"))
            _set_if("sbj", parsed.get("sbj") or parsed.get("sbj_num"))
            _set_if("ccy", parsed.get("ccy"))
            _set_if("dt", parsed.get("dt"))
            _set_if("plan_prompt", parsed.get("plan_prompt") or parsed.get("planPrompt"))
            _set_if("user_selected_steps", parsed.get("user_selected_steps") or parsed.get("selectedSteps"))
            _set_if("mode", parsed.get("mode"))
            _set_if("sql_request", parsed.get("sql_request") or parsed.get("sqlRequest") or parsed.get("sql_question"))

    if "dt" in payload:
        payload["dt"] = normalize_dt_value(payload["dt"])
    return payload


def _run_sql_graph(question: str) -> OutputState:
    if not question:
        return {
            "discrepancies": [],
            "classes": {},
            "results": [],
            "summary": {"mode": "sql", "error": "missing sql_request"},
            "plan_steps": [],
            "user_selected_steps": [],
            "log_lines": ["缺少 sql_request，无法生成 SQL。"],
            "sql_query": None,
            "sql_result": None,
            "sql_messages": None,
        }
    try:
        from app.core.agent.graph.sql_graph import run_sql_graph
    except Exception as exc:
        return {
            "discrepancies": [],
            "classes": {},
            "results": [],
            "summary": {"mode": "sql", "error": str(exc)},
            "plan_steps": [],
            "user_selected_steps": [],
            "log_lines": [f"SQL graph unavailable: {exc}"],
            "sql_query": None,
            "sql_result": None,
            "sql_messages": None,
        }
    result = run_sql_graph(question)
    execution = result.get("sql_result")
    if isinstance(execution, str) and (execution.strip() == "[]" or not execution.strip()):
        execution = "No rows found; the underlying tables may be missing data for the requested org/sbj/ccy/dt or there were no transactions that day."
    return {
        "discrepancies": [],
        "classes": {},
        "results": [],
        "summary": {"mode": "sql"},
        "plan_steps": [],
        "user_selected_steps": [],
        "log_lines": result.get("sql_messages", []) or [],
        "sql_query": result.get("sql_query"),
        "sql_result": execution,
        "sql_messages": result.get("sql_messages"),
    }


@tool(parse_docstring=True)
def generate_sql_for_reconciliation(sql_request: str) -> Dict[str, Any]:
    """Generate and execute SQL to investigate reconciliation data.

    Args:
        sql_request: Natural language request about reconciliation data (org/sbj/ccy/dt).

    Returns:
        SQL text plus execution result and messages.
    """
    return _run_sql_graph(sql_request)


DEFAULT_TOOLS: List[BaseTool | Callable | Dict[str, Any]] = [analyze_react_bank, generate_sql_for_reconciliation]
DEFAULT_SUBAGENTS: List[Dict[str, Any]] = [
    {
        "name": "planner",
        "description": "Break down reconciliation tasks into ordered steps and remind when parameters are missing.",
        "system_prompt": "You are a reconciliation planner. Propose concise, actionable steps, ask for missing org/sbj/ccy/dt, and keep outputs short.",
        "tools": [],
    },
    {
        "name": "sql-helper",
        "description": "Generate and execute SQL to inspect reconciliation data based on org/sbj/ccy/dt.",
        "system_prompt": "You are a SQL specialist. Given a reconciliation question, generate precise SQL and summarize the result briefly.",
        "tools": [generate_sql_for_reconciliation],
    },
]


def _direct_fin_agent_node(state: Dict[str, Any]) -> OutputState:
    payload = _extract_input_payload(state)
    mode = str(payload.get("mode") or "").lower()
    sql_request = payload.get("sql_request") or payload.get("query") or ""
    if mode == "sql" or sql_request:
        return _run_sql_graph(str(sql_request))
    initial: AgentState = {
        "target_org": payload.get("org", ""),
        "target_sbj": payload.get("sbj", ""),
        "target_ccy": payload.get("ccy", ""),
        "target_dt": payload.get("dt", ""),
        "plan_prompt": payload.get("plan_prompt", "") or "",
        "user_selected_steps": payload.get("user_selected_steps") or [],
    }
    final_state = _run_pipeline(initial)
    return _build_output(final_state)


def build_direct_fin_agent() -> CompiledStateGraph:
    builder = StateGraph(dict, output_schema=OutputState)
    builder.add_node("run_pipeline", _direct_fin_agent_node)
    builder.set_entry_point("run_pipeline")
    builder.add_edge("run_pipeline", END)
    return builder.compile()


def _maybe_add_local_deepagents_path() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    candidate = repo_root / "deepagents-master" / "libs" / "deepagents"
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


def _load_deepagents_middlewares():
    _maybe_add_local_deepagents_path()
    try:
        filesystem_mod = importlib.import_module("deepagents.middleware.filesystem")
        patch_mod = importlib.import_module("deepagents.middleware.patch_tool_calls")
        subagents_mod = importlib.import_module("deepagents.middleware.subagents")
        FilesystemMiddleware = getattr(filesystem_mod, "FilesystemMiddleware")
        PatchToolCallsMiddleware = getattr(patch_mod, "PatchToolCallsMiddleware")
        SubAgentMiddleware = getattr(subagents_mod, "SubAgentMiddleware")
    except Exception as exc:  # pragma: no cover
        logging.warning("deepagents middleware unavailable: %s", exc)
        return None, None, None
    return FilesystemMiddleware, SubAgentMiddleware, PatchToolCallsMiddleware


def _get_summarization_settings(agent_model: BaseChatModel) -> Tuple[Tuple[str, float], Tuple[str, float | int]]:
    trigger: Tuple[str, float] = ("tokens", 170000)
    keep: Tuple[str, float | int] = ("messages", 6)
    profile = getattr(agent_model, "profile", None)
    if isinstance(profile, dict) and isinstance(profile.get("max_input_tokens"), int):
        trigger = ("fraction", 0.85)
        keep = ("fraction", 0.10)
    return trigger, keep


def _optional_anthropic_prompt_cache():
    try:
        anthropic_mod = importlib.import_module("langchain_anthropic.middleware")
        AnthropicPromptCachingMiddleware = getattr(anthropic_mod, "AnthropicPromptCachingMiddleware")
    except Exception:  # pragma: no cover
        return None
    return AnthropicPromptCachingMiddleware(unsupported_model_behavior="ignore")


def _create_summarization_middleware(
    agent_model: BaseChatModel,
    trigger: Tuple[str, float],
    keep: Tuple[str, float | int],
) -> SummarizationMiddleware:
    try:
        return SummarizationMiddleware(
            model=agent_model,
            trigger=trigger,
            keep=keep,
            trim_tokens_to_summarize=None,
        )
    except TypeError:
        return SummarizationMiddleware(model=agent_model)


def _build_deepagent_middlewares(
    agent_model: BaseChatModel,
    tools: Sequence[BaseTool | Callable | Dict[str, Any]],
    subagents: Optional[List[Dict[str, Any]]],
    interrupt_on: Optional[Dict[str, bool | InterruptOnConfig]],
) -> List[Any]:
    FilesystemMiddleware, SubAgentMiddleware, PatchToolCallsMiddleware = _load_deepagents_middlewares()
    trigger, keep = _get_summarization_settings(agent_model)
    anthropic_cache = _optional_anthropic_prompt_cache()

    middlewares: List[Any] = [TodoListMiddleware()]
    if FilesystemMiddleware:
        middlewares.append(FilesystemMiddleware())

    if SubAgentMiddleware:
        subagent_defaults: List[Any] = [TodoListMiddleware()]
        if FilesystemMiddleware:
            subagent_defaults.append(FilesystemMiddleware())
        subagent_defaults.append(_create_summarization_middleware(agent_model, trigger, keep))
        if anthropic_cache:
            subagent_cache = _optional_anthropic_prompt_cache()
            if subagent_cache:
                subagent_defaults.append(subagent_cache)
        if PatchToolCallsMiddleware:
            subagent_defaults.append(PatchToolCallsMiddleware())
        middlewares.append(
            SubAgentMiddleware(
                default_model=agent_model,
                default_tools=tools,
                subagents=subagents or [],
                default_middleware=subagent_defaults,
                default_interrupt_on=interrupt_on,
                general_purpose_agent=True,
            )
        )

    middlewares.append(_create_summarization_middleware(agent_model, trigger, keep))
    if anthropic_cache:
        middlewares.append(anthropic_cache)
    if PatchToolCallsMiddleware:
        middlewares.append(PatchToolCallsMiddleware())
    if interrupt_on:
        middlewares.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))
    return middlewares


def create_react_bank_agent(
    model_override: Optional[BaseChatModel] = None,
    tools: Optional[Sequence[BaseTool | Callable | Dict[str, Any]]] = None,
    system_prompt: Optional[str] = None,
    subagents: Optional[List[Dict[str, Any]]] = None,
    interrupt_on: Optional[Dict[str, bool | InterruptOnConfig]] = None,
    debug: bool = False,
    name: Optional[str] = None,
) -> CompiledStateGraph:
    agent_model = model_override or model
    toolset = list(tools) if tools is not None else list(DEFAULT_TOOLS)
    subagent_set = list(subagents) if subagents is not None else list(DEFAULT_SUBAGENTS)
    prompt = system_prompt or REACT_BANK_SYSTEM_PROMPT

    _maybe_add_local_deepagents_path()
    try:
        deepagents_mod = importlib.import_module("deepagents")
        _create_deep_agent = getattr(deepagents_mod, "create_deep_agent")
    except Exception as exc:  # pragma: no cover
        logging.warning("deepagents.create_deep_agent unavailable: %s", exc)
        middlewares = _build_deepagent_middlewares(agent_model, toolset, subagent_set, interrupt_on)
        return create_agent(
            agent_model,
            system_prompt=f"{prompt}\n\n{BASE_AGENT_PROMPT}",
            tools=toolset,
            middleware=middlewares,
            debug=debug,
            name=name,
        ).with_config({"recursion_limit": 1000})

    return _create_deep_agent(
        model=agent_model,
        tools=toolset,
        system_prompt=prompt,
        subagents=subagent_set,
        interrupt_on=interrupt_on,
        debug=debug,
        name=name,
    )


_DEEP_AGENT: Optional[CompiledStateGraph] = None


def get_react_bank_agent() -> CompiledStateGraph:
    global _DEEP_AGENT
    if _DEEP_AGENT is None:
        direct_flag = os.getenv("FIN_AGENT_DIRECT", "true").lower()
        use_direct = direct_flag in {"1", "true", "yes"}
        _DEEP_AGENT = build_direct_fin_agent() if use_direct else create_react_bank_agent()
    return _DEEP_AGENT


fin_agent = get_react_bank_agent()


def build_graph() -> CompiledStateGraph:
    return get_react_bank_agent()


def run_react() -> Dict[str, Any]:
    final_state = _run_pipeline({})
    return _build_output(final_state)


def run_react_single(org: str, sbj: str, ccy: str, dt: str) -> Dict[str, Any]:
    initial: AgentState = {
        "target_org": org,
        "target_sbj": sbj,
        "target_ccy": ccy,
        "target_dt": dt,
    }
    final_state = _run_pipeline(initial)
    return _build_output(final_state)


if __name__ == "__main__":
    sample_org = os.environ.get("SAMPLE_ORG", "001170661")
    sample_sbj = os.environ.get("SAMPLE_SBJ", "01018114")
    sample_ccy = os.environ.get("SAMPLE_CCY", "DUS")
    sample_dt = os.environ.get("SAMPLE_DT", "20250601")

    try:
        result = run_react_single(sample_org, sample_sbj, sample_ccy, sample_dt)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"执行出错: {exc}")
        import traceback

        traceback.print_exc()
