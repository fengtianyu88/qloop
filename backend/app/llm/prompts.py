"""Prompt templates for the three LLM review types.

Each template contains a ``{content}`` placeholder that is filled with the
prepared review content (code package summary / parsed document text) before
being sent to the LLM. All templates instruct the model to respond with a
strict JSON structure so the result can be parsed programmatically.
"""

from app.models.review import ReviewType


# ---------------------------------------------------------------------------
# Shared output-format instructions
# ---------------------------------------------------------------------------
_OUTPUT_FORMAT = """\
你必须以严格的 JSON 格式输出评审结果，不要输出任何额外文字或解释。JSON 结构如下：
{{
  "total_score": <0-100 之间的整数，综合评分>,
  "dimension_scores": {{
    "<维度1名称>": <0-100 的分数>,
    "<维度2名称>": <0-100 的分数>
  }},
  "conclusion": "<passed 或 failed>",
  "suggestions": "<针对改进的具体建议，多条用换行分隔>",
  "risk_points": "<识别出的风险点，多条用换行分隔，若无风险可填空字符串>"
}}
"""


# ---------------------------------------------------------------------------
# 1. Code review prompt
# ---------------------------------------------------------------------------
CODE_REVIEW_PROMPT = """\
你是一位资深的代码评审专家。请对以下提交的代码包进行严格的代码评审。

评审维度（每项按 0-100 打分）：
1. 代码质量：命名规范、注释完整性、代码结构清晰度、是否符合编码规范。
2. 变更合理性：变更是否与变更点说明一致、是否存在冗余/无关变更、变更是否引入回归风险。
3. 安全性：是否存在缓冲区溢出、空指针、未初始化变量、硬编码密钥、输入校验缺失等安全隐患。
4. 可维护性：模块化程度、耦合度、可读性、是否易于后续扩展与维护。

请基于以下内容进行评审：

{content}

""" + _OUTPUT_FORMAT


# ---------------------------------------------------------------------------
# 2. Test report review prompt
# ---------------------------------------------------------------------------
TEST_REPORT_REVIEW_PROMPT = """\
你是一位资深的测试评审专家。请对以下提交的测试报告进行严格评审。

评审维度（每项按 0-100 打分）：
1. 测试覆盖率：功能点覆盖是否完整、边界条件与异常路径是否被覆盖、覆盖率数据是否充分。
2. 测试完整性：测试用例是否齐全、测试环境与数据是否描述清楚、是否包含回归测试。
3. 缺陷管理：缺陷是否被完整记录、严重等级划分是否合理、缺陷修复与验证闭环是否清晰。
4. 文档质量：报告结构是否规范、结论是否明确、数据与图表是否准确可追溯。

请基于以下测试报告内容进行评审：

{content}

""" + _OUTPUT_FORMAT


# ---------------------------------------------------------------------------
# 3. Expert report review prompt
# ---------------------------------------------------------------------------
EXPERT_REPORT_REVIEW_PROMPT = """\
你是一位资深的专家评审委员会成员。请对以下提交的专家评审报告进行 meta 评审（即对专家评审工作的质量进行评审）。

评审维度（每项按 0-100 打分）：
1. 评审深度：是否深入分析了算法原理、实现细节与潜在影响，是否停留在表面。
2. 评审准确性：技术判断是否正确、引用的标准与数据是否准确、结论是否有充分依据。
3. 建设性：是否提出了具体可行的改进建议、建议是否有助于提升软件质量。
4. 规范性：报告格式是否规范、术语是否统一、逻辑是否清晰、是否签署完整。

请基于以下专家评审报告内容进行评审：

{content}

""" + _OUTPUT_FORMAT


# ---------------------------------------------------------------------------
# Mapping from ReviewType.value -> prompt template
# ---------------------------------------------------------------------------
PROMPT_MAP = {
    ReviewType.CODE_REVIEW.value: CODE_REVIEW_PROMPT,
    ReviewType.TEST_REPORT_REVIEW.value: TEST_REPORT_REVIEW_PROMPT,
    ReviewType.EXPERT_REPORT_REVIEW.value: EXPERT_REPORT_REVIEW_PROMPT,
}
