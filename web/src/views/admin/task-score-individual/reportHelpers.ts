import type { TaskScoreIndividualAnalysisResult } from '../../../api/admin/task-score-individual-analysis'
import { conditionLabel, formatNumber } from '../task-score/reportHelpers'

function esc(value: unknown): string {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function buildIndividualTaskScoreReportHtml(report: TaskScoreIndividualAnalysisResult): string {
  const conditionHeaders = report.conditions.map((condition) => `<th>${esc(conditionLabel(condition))}</th>`).join('')
  const statsCells = report.conditions.map((condition) => {
    const item = report.individual_stats.find((row) => row.condition === condition)
    return `<td>个人 n=${item?.n ?? 0}<br>M=${formatNumber(item?.mean ?? null)}; SD=${formatNumber(item?.sd ?? null)}<br>Median=${formatNumber(item?.median ?? null)}; Range=${formatNumber(item?.min ?? null)}–${formatNumber(item?.max ?? null)}</td>`
  }).join('')
  const taskRows = report.task_summaries.map((task) => `<tr><th>${esc(task.task_id)}</th>${report.conditions.map((condition) => {
    const item = task.conditions.find((row) => row.condition === condition)
    return `<td>n=${item?.n ?? 0}; M=${formatNumber(item?.mean ?? null)}; SD=${formatNumber(item?.sd ?? null)}</td>`
  }).join('')}</tr>`).join('')
  const pairRows = report.pairwise_tests.length
    ? report.pairwise_tests.map((item) => `<tr><td>${esc(conditionLabel(item.condition_a))}</td><td>${esc(conditionLabel(item.condition_b))}</td><td>${formatNumber(item.mean_difference)}</td><td>${formatNumber(item.p_value)}</td><td>${formatNumber(item.p_value_adjusted)}</td><td>${item.significant ? '是' : '否'}</td></tr>`).join('')
    : `<tr><td colspan="6">${report.conditions.length < 3 ? '当前模式无需三条件两两比较' : '总体检验未达到显著水平，不执行事后两两比较'}</td></tr>`
  const detailRows = report.observations.map((item) => `<tr><td>${esc(conditionLabel(item.condition))}</td><td>${esc(item.task_id)}</td><td>${esc(item.group_id)}</td><td>${esc(item.participant_id)}</td><td>${formatNumber(item.score)}</td></tr>`).join('')
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>个人任务成绩分析报告</title><style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#172033;margin:32px;line-height:1.55}h1{margin-bottom:4px}h2{margin-top:28px}p.note{color:#526071;background:#f8fafc;padding:12px 14px;border-left:4px solid #2563eb}table{width:100%;border-collapse:collapse;margin:12px 0}th,td{border:1px solid #dbe3ee;padding:8px 10px;text-align:left;vertical-align:top}th{background:#f4f7fb}.ok{color:#047857}.warning{color:#b45309}@media print{body{margin:12mm}}
</style></head><body><h1>个人任务成绩分析报告</h1><p>生成时间：${esc(new Date().toLocaleString('zh-CN'))}</p><p class="note">个人分数越低表示表现越好。本报告展示个人分数，但条件推断以小组为聚类和置换单位，不把同组成员视为独立实验单位。报告明细仅使用参与者编码，不导出姓名。</p>
<h2>样本</h2><table><tr><th>总个人数</th><td>${report.total_individuals}</td><th>总小组数</th><td>${report.total_groups}</td></tr>${report.conditions.map((condition) => `<tr><th>${esc(conditionLabel(condition))}</th><td>${report.individuals_by_condition[condition] ?? 0} 人</td><th>独立小组</th><td>${report.groups_by_condition[condition] ?? 0} 组</td></tr>`).join('')}</table>
<h2>个人分数描述统计</h2><table><tr><th>指标</th>${conditionHeaders}</tr><tr><th>个人分数</th>${statsCells}</tr></table>
<h2>AIS 一致性校验</h2><p class="${report.ais_consistency.status}">${esc(report.ais_consistency.note)}；核对 ${report.ais_consistency.checked_groups} 组，最大绝对差 ${formatNumber(report.ais_consistency.max_absolute_difference)}。</p>
<h2>按任务分层</h2><table><tr><th>任务</th>${conditionHeaders}</tr>${taskRows}</table>
<h2>小组聚类置换检验</h2><table><tr><th>方法</th><th>统计量</th><th>p</th><th>效应量</th><th>状态</th></tr><tr><td>${esc(report.statistical_test.method)}</td><td>${esc(report.statistical_test.statistic_name)}=${formatNumber(report.statistical_test.statistic)}</td><td>${formatNumber(report.statistical_test.p_value)}</td><td>${esc(report.statistical_test.effect_size_name)}=${formatNumber(report.statistical_test.effect_size)}</td><td>${esc(report.statistical_test.status)}</td></tr></table><p class="note">${esc(report.statistical_test.note)}</p>
<h2>两两比较</h2><table><tr><th>条件A</th><th>条件B</th><th>均值差(B−A)</th><th>原始p</th><th>Holm校正后p</th><th>显著</th></tr>${pairRows}</table>
<h2>匿名个人明细</h2><table><tr><th>条件</th><th>任务</th><th>小组</th><th>参与者编码</th><th>分数</th></tr>${detailRows}</table></body></html>`
}
