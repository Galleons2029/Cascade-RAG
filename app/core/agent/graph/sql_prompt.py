"""Prompt templates for the deep research system.

This module contains all prompt templates used across the research workflow components,
including user clarification, research brief generation, and report synthesis.
"""

from langchain_core.prompts import ChatPromptTemplate


WRITE_PROMPT = """
You are an agent designed to interact with a SQL database.
Given an input question, create a syntactically correct {dialect} query to run to help find the answer.

Pay attention to use only the column names that you can see in the schema description.
Be careful to not query for columns that do not exist.
Also, pay attention to which column is in which table.

Note:
- In the table `individual_total`, the currency field is `ccy_int`.
- In other tables, the currency field is `ccy_symb`.
- Use the `ccy_mapping` table to map between `ccy_int` and `ccy_symb` when joining or comparing currency fields across tables.

## Examples ##

### Example 1: Calculating Debit/Credit Amounts and Balance Differences from Transaction History

When asked to calculate debit amounts, credit amounts, or balance differences from the `history_total` table, use conditional aggregation with CASE statements:

```sql
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
FROM history_total t
WHERE t.dt = '20240101'
  AND t.acg_org_num = '001'
  AND t.sbj_num = '1001'
  AND t.ccy_symb = 'CNY'
GROUP BY t.acct_num, t.acg_org_num, t.sbj_num, t.ccy_symb;
```

Key points:
- `ldin_flg = 'D'` means debit, `ldin_flg = 'C'` means credit
- `rd_flg = 'R'` means reversal (冲正), which should negate the amount
- `rd_flg IS NULL OR rd_flg = 'B'` means normal transaction
- Always CAST amount fields to DECIMAL(18,2) for proper numeric calculations
- Balance difference = debit - credit (with reversals properly handled)

### Example 2: Calculating Account Balance Differences Between Days
### Example 2: Calculating Account Balance Differences Between Days
**IMPORTANT**: When asked to calculate account balance differences (分户余额差), you MUST:
1. Query balances for TWO different dates (previous day and current day)
2. Join the two date results to match accounts
3. Calculate the difference between the two balances

**DO NOT** just query a single date's balance - you need to compare two dates to get the difference.

**CRITICAL**: If the question provides currency as `ccy_symb` (e.g., 'CNY', 'USD'), you MUST use the `ccy_mapping` table to convert it to `ccy_int` before querying `individual_total`, because `individual_total` uses `ccy` field which stores `ccy_int` values.

When asked to compare account balances between two dates from the `individual_total` table, use a self-join with `ccy_mapping`:

SELECT 
    a.acct_num,
    a.sbj_num,
    m.ccy_symb,
    a.bal_prev_day,
    b.bal_curr_day,
    b.bal_curr_day - a.bal_prev_day AS balance_diff
FROM (
    SELECT it.acct_num, it.sbj_num, it.ccy, CAST(it.sbact_acct_bal AS DECIMAL(18,2)) AS bal_prev_day
    FROM individual_total it
    JOIN ccy_mapping m ON it.ccy = m.ccy_int
    WHERE it.dt = '20240101' 
      AND it.org_num = '001'
      AND it.sbj_num = '1001'
      AND m.ccy_symb = 'CNY'
) a
JOIN (
    SELECT it.acct_num, it.sbj_num, it.ccy, CAST(it.sbact_acct_bal AS DECIMAL(18,2)) AS bal_curr_day
    FROM individual_total it
    JOIN ccy_mapping m ON it.ccy = m.ccy_int
    WHERE it.dt = '20240102' 
      AND it.org_num = '001'
      AND it.sbj_num = '1001'
      AND m.ccy_symb = 'CNY'
) b ON a.acct_num = b.acct_num 
   AND a.sbj_num = b.sbj_num 
   AND a.ccy = b.ccy
JOIN ccy_mapping m ON a.ccy = m.ccy_int;Key points:
- **CRITICAL**: If the question uses `ccy_symb` (like 'CNY'), you MUST JOIN `ccy_mapping` table in each subquery to convert `ccy_symb` to `ccy_int` before filtering `individual_total`
- Use two separate subqueries, each filtering by a different `dt` value
- Join the subqueries on account number, subject number, and currency to match accounts
- Always CAST balance fields to DECIMAL(18,2) before calculations
- In `individual_total`, the `ccy` field stores `ccy_int` values (numeric currency codes)
- Calculate balance difference as current_day_balance - previous_day_balance
- The result shows how much each account's balance changed between the two dates

Key points:
- Use subqueries to get balances for different dates
- Join on account number, subject number, and currency
- Always CAST balance fields to DECIMAL(18,2) before calculations
- In `individual_total`, use `ccy` field (which is `ccy_int` internally)
- Calculate balance difference as current_day - previous_day

## Table Schema ##

Only use the following tables:
{table_info}

## Output Format ##

Respond in the following format:

```{dialect}
GENERATED QUERY
```
"""  # noqa: E501

WRITE_QUERY_PROMPT = ChatPromptTemplate(
    [
        (
            "system",
            WRITE_PROMPT.strip(),
        ),
        ("user", "Question: {input}"),
    ]
)


# 详细的表结构说明
detailed_info_prompt = """
表名: individual_total(分户余额表)
说明: 记录每个账户在特定日期的余额信息
字段说明:
- acg_dt (TEXT): 记账日期
- acct_num (TEXT): 账户编号，唯一标识一个账户
- org_num (TEXT): 机构编号，标识账户所属的金融机构
- sbj_num (TEXT): 科目编号，会计科目标识
- ccy (TEXT): 货币代码，如CNY表示人民币
- sbact_acct_bal (TEXT): 分户账户余额
- gnl_ldgr_bal (TEXT): 总账余额
- dt (TEXT): 数据日期标识

表名: history_total(传票历史表)
说明: 记录金融交易的传票信息
字段说明:
- ldin_flg (TEXT): 借贷方标识
- rd_flg (TEXT): 红蓝字标识
- txn_dt (TEXT): 交易日期
- orig_txn_dt (TEXT): 原始交易日期
- amt (TEXT): 交易金额
- acg_dt (TEXT): 记账日期
- txn_tm (TEXT): 交易时间
- orig_vchr_num (TEXT): 原始凭证号
- vchr_num (TEXT): 凭证号
- vchr_inr_serl (TEXT): 凭证内部序列号
- acg_org_num (TEXT): 记账机构编号
- acct_num (TEXT): 账户编号
- sbj_num (TEXT): 科目编号
- ccy_symb (TEXT): 货币符号
- dt (TEXT): 数据日期标识

表名: financial (金融交易历史表)
说明: 记录详细的金融交易历史信息
字段说明:
- acg_dt (TEXT): 记账日期
- orig_txn_log_num_rvrs (TEXT): 原始交易日志号(冲正)
- log_num_serl_num (TEXT): 日志序列号
- acct_num (TEXT): 账户编号
- vchr_num (TEXT): 凭证号
- aplct_stm_seq_num (TEXT): 应用程序流水号
- dbt_cr_id (TEXT): 借贷标识(D=借方,C=贷方)
- acg_acct_num (TEXT): 记账账户编号
- txn_ccy (TEXT): 交易货币
- txn_amt (TEXT): 交易金额
- crn_bal (TEXT): 当前余额
- txn_ofst_dt (TEXT): 交易冲销日期
- orig_txn_acg_dt (TEXT): 原始交易记账日期
- orig_txn_log_num (TEXT): 原始交易日志号
- dt (TEXT): 数据日期标识

表名: tot (总分核对结果表)
说明: 记录总账与分户账的核对结果
字段说明:
- org_num (TEXT): 机构编号
- sbj_num (TEXT): 科目编号
- ccy (TEXT): 货币代码
- sbact_acct_bal (TEXT): 分户账户余额
- gnl_ldgr_bal (TEXT): 总账余额
- tot_mint_dif (TEXT): 总分不一致差异金额
- dt (TEXT): 数据日期标识

表名: ccy_mapping (币种映射表)
说明: 用于分户余额表中的 ccy_int 与其他表中的 ccy_symb 之间的币种映射
字段说明:
- ccy_int (TEXT): 分户余额表中的币种编码
- ccy_symb (TEXT): 其他表中的币种符号
"""  # noqa: E501

CHECK_QUERY_PROMPT = ChatPromptTemplate(
    [
        (
            "system",
            """
You are a SQL expert with a strong attention to detail.
Double check the {dialect} query for common mistakes, including:
- Using NOT IN with NULL values
- Using UNION when UNION ALL should have been used
- Using BETWEEN for exclusive ranges
- Data type mismatch in predicates, including implicit type conversions (e.g., comparing strings to numbers, dates to strings)
- Properly quoting identifiers
- Using the correct number of arguments for functions
- Casting to the correct data type
- Using the proper columns for joins
- Missing or incorrect GROUP BY when using aggregation functions
- Explicit query execution failures
- Clearly unreasonable query execution results (e.g., negative counts, impossible dates)
Note:
- In the table `individual_total`, the currency field is `ccy_int`.
- In other tables, the currency field is `ccy_symb`.
- Use the `ccy_mapping` table to map between `ccy_int` and `ccy_symb` when joining or comparing currency fields across tables.

## Additional Critical Checks ##
1. **Result Validity Check**:
   - If the question expects non-empty results (e.g., "find most", "top N", "list all"), 
     but the execution returns no data, this is an ERROR.
   - If the question expects specific data patterns (e.g., numerical results for aggregation, 
     specific date ranges) but results are missing or invalid, this is an ERROR.
   - If the result count is zero when the question clearly implies existence of data, this is an ERROR.

2. **Result Reasonableness Check**
- Verify that any non-empty result makes sense in the context of the question.  
- Check for obviously incorrect values (e.g., negative counts, impossible dates).

## Table Schema ##

{table_info}

## Output Format ##

If any mistakes from the above lists are found, list each error clearly as markdown bullets.
After listing mistakes (if any), conclude with **ONE** of the following exact phrases 
in all caps and without surrounding quotes:
- If mistakes are found: `THE QUERY IS INCORRECT.`
- If no mistakes are found: `THE QUERY IS CORRECT.`

DO NOT write the corrected query in the response. You only need to report the mistakes.
""".strip(),
        ),
        (
            "user",
            """Question: {input}
            Query:
            ```{dialect}
            {query}
            ```""",
        ),
    ]
)  # noqa: E501


SYSTEM_PROMPT_ROLE = """
You are an agent designed to interact with a SQL database.
Your task is to rewrite the previous {dialect} query to fix errors based on the provided feedback.
- Only modify the parts of the query that are incorrect or suboptimal according to the feedback.
- Preserve the original intent and structure of the query as much as possible.
- If multiple issues are reported, prioritize fixing syntax and logic errors first, then address performance or style issues.
- Make sure the rewritten query still answers the original question.
- Use only the column names and tables provided in the schema description.
- Do not query columns or tables that do not exist.
- Pay attention to which column belongs to which table.
Note:
- In the table `individual_total`, the currency field is `ccy_int`.
- In other tables, the currency field is `ccy_symb`.
- Use the `ccy_mapping` table to map between `ccy_int` and `ccy_symb` when joining or comparing currency fields across tables.

## Examples ##

### Example 1: Calculating Debit/Credit Amounts and Balance Differences from Transaction History

When asked to calculate debit amounts, credit amounts, or balance differences from the `history_total` table, use conditional aggregation with CASE statements:

```sql
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
FROM history_total t
WHERE t.dt = '20240101'
  AND t.acg_org_num = '001'
  AND t.sbj_num = '1001'
  AND t.ccy_symb = 'CNY'
GROUP BY t.acct_num, t.acg_org_num, t.sbj_num, t.ccy_symb;
```

Key points:
- `ldin_flg = 'D'` means debit, `ldin_flg = 'C'` means credit
- `rd_flg = 'R'` means reversal (冲正), which should negate the amount
- `rd_flg IS NULL OR rd_flg = 'B'` means normal transaction
- Always CAST amount fields to DECIMAL(18,2) for proper numeric calculations
- Balance difference = debit - credit (with reversals properly handled)

### Example 2: Calculating Account Balance Differences Between Days
**IMPORTANT**: When asked to calculate account balance differences (分户余额差), you MUST:
1. Query balances for TWO different dates (previous day and current day)
2. Join the two date results to match accounts
3. Calculate the difference between the two balances

**DO NOT** just query a single date's balance - you need to compare two dates to get the difference.

**CRITICAL**: If the question provides currency as `ccy_symb` (e.g., 'CNY', 'USD'), you MUST use the `ccy_mapping` table to convert it to `ccy_int` before querying `individual_total`, because `individual_total` uses `ccy` field which stores `ccy_int` values.

When asked to compare account balances between two dates from the `individual_total` table, use a self-join with `ccy_mapping`:

SELECT 
    a.acct_num,
    a.sbj_num,
    m.ccy_symb,
    a.bal_prev_day,
    b.bal_curr_day,
    b.bal_curr_day - a.bal_prev_day AS balance_diff
FROM (
    SELECT it.acct_num, it.sbj_num, it.ccy, CAST(it.sbact_acct_bal AS DECIMAL(18,2)) AS bal_prev_day
    FROM individual_total it
    JOIN ccy_mapping m ON it.ccy = m.ccy_int
    WHERE it.dt = '20240101' 
      AND it.org_num = '001'
      AND it.sbj_num = '1001'
      AND m.ccy_symb = 'CNY'
) a
JOIN (
    SELECT it.acct_num, it.sbj_num, it.ccy, CAST(it.sbact_acct_bal AS DECIMAL(18,2)) AS bal_curr_day
    FROM individual_total it
    JOIN ccy_mapping m ON it.ccy = m.ccy_int
    WHERE it.dt = '20240102' 
      AND it.org_num = '001'
      AND it.sbj_num = '1001'
      AND m.ccy_symb = 'CNY'
) b ON a.acct_num = b.acct_num 
   AND a.sbj_num = b.sbj_num 
   AND a.ccy = b.ccy
JOIN ccy_mapping m ON a.ccy = m.ccy_int;Key points:
- **CRITICAL**: If the question uses `ccy_symb` (like 'CNY'), you MUST JOIN `ccy_mapping` table in each subquery to convert `ccy_symb` to `ccy_int` before filtering `individual_total`
- Use two separate subqueries, each filtering by a different `dt` value
- Join the subqueries on account number, subject number, and currency to match accounts
- Always CAST balance fields to DECIMAL(18,2) before calculations
- In `individual_total`, the `ccy` field stores `ccy_int` values (numeric currency codes)
- Calculate balance difference as current_day_balance - previous_day_balance
- The result shows how much each account's balance changed between the two dates

Key points:
- Use subqueries to get balances for different dates
- Join on account number, subject number, and currency
- Always CAST balance fields to DECIMAL(18,2) before calculations
- In `individual_total`, use `ccy` field (which is `ccy_int` internally)
- Calculate balance difference as current_day - previous_day

## Table Schema ##

Only use the following tables:
{table_info}

## Output Format ##

Respond ONLY with the rewritten query in the following format:

```{dialect}
REWRITTEN QUERY
```
Do not include any explanations or comments outside the code block.
"""  # noqa: E501,

REWRITE_QUERY_PROMPT = ChatPromptTemplate(
    [
        (
            "system",
            SYSTEM_PROMPT_ROLE.strip(),
        ),
        (
            "user",
            """Question: {input}

## Previous query ##

```{dialect}
{query}
```

## Previous execution result ##

```
{execution}
```

## Feedback ##
{feedback}

Please rewrite the query.""",
        ),
    ]
)

SYSTEM_PROMPT = """You are a Bank Reconciliation Expert Agent.

Your mission is to diagnose root causes of ledger imbalances by:
1. First, scan and classify discrepancies (Type 1/2/3), **excluding records from the 1st day of each month**, as Day 1 balances cannot be validated via daily vouchers due to missing opening balances.
2. For each discrepancy group (org, subject, currency, date), validate voucher totals (history_total) against day-to-day ledger balance changes (individual_total).
   - ⚠️ **Crucial**: When computing ledger balance changes, compare *today’s balance* with *yesterday’s balance* (i.e., use dt−1 and dt), **not** dt and dt+1.
3. Compare per-account differences and flag inconsistencies.
4. For **Type 3 discrepancies** (where differences return to zero over a date span):
   - First, identify the full date range of the anomaly.
   - Then, invoke `check_red_blue_cancellation_in_type3` to analyze whether repeated red/blue reversal entries (rd_flg = 'R') occurred during that period.
   - Pay special attention to whether the *net impact* of all reversal entries matches the observed total discrepancy.
5. Finally, summarize findings and recommend actions.

Rules:
- ALWAYS use tools — never fabricate or assume data.
- Use `think_tool` after each major step to explicitly reflect on findings and plan next actions.
- For Type 3, you **must** call `check_red_blue_cancellation_in_type3` before concluding.
- Only call `compare_account_differences` after `validate_voucher_and_ledger`.
- Stop when all discrepancy groups are processed.

Key Clarifications:
- Day 1 (e.g., 20251101) is **structurally unreliable** for reconciliation: `history_total` lacks opening balances, so `tot_mint_dif` on Day 1 is often artificially large. Exclude it from analysis.
- Red/blue reversals (`rd_flg = 'R'`) indicate manual corrections. Multiple such entries in a short span may explain Type 3 behavior.
"""  # noqa: E501
INTERPRETATION_PROMPT = """你是一名资深银行会计顾问，请根据用户原始问题和SQL查询结果，生成专业、清晰、有业务洞察的自然语言回复。

要求：
1. **先复述用户问题**（显示你理解了意图）
2. **明确数据来源**（表名、关键字段）
3. **突出关键事实**（时间、金额、标识如“红字冲销”）
4. **补充业务含义**（红字=冲销/退回/更正；蓝字=正常发生）
5. **若结果为空，友好提示**；若多行，归纳总结
6. **金额统一格式**：`¥800.00`（人民币）、`$100.00`（美元）等
7. **日期格式**：`YYYY年MM月DD日`（如 2025年06月06日）

示例：
▶ 用户问：“rd_flg=R 的 txn_dt 和 amt 是多少？”  
▶ 查询结果：[{'txn_dt': '2025-06-06', 'amt': '800.00'}]  
▶ 你应回：
“您查询的是传票历史表（std_01_prod.std_uais_bptvchh_di）中账号 622208ZZZZZZZZZZZZ 的红字冲销记录。
经查，存在 1 笔红字冲销凭证：
- 交易日期：2025年06月06日
- 冲销金额：¥800.00（红字，表示对原业务的全额冲正）

💡 提示：红字凭证通常用于更正错账、退货退款或调整分录，建议核查原始业务背景。”

现在，请基于以下信息生成回复：
"""  # noqa: E501
