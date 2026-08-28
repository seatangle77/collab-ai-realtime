import type { TaskScoreIndividualAnalysisResult } from '../../../api/admin/task-score-individual-analysis'
import { conditionLabel, formatNumber, taskLabel } from '../task-score/reportHelpers'

function esc(value: unknown): string {
  return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

const positionLabel = (position: string) => ({ best: '原最佳成员', middle: '原中间成员', weakest: '原最弱成员' } as Record<string, string>)[position] ?? position

export function buildIndividualTaskScoreReportHtml(report: TaskScoreIndividualAnalysisResult): string {
  const conditionHeaders = report.conditions.map((condition) => `<th>${esc(conditionLabel(condition))}</th>`).join('')
  const improvementRows = report.improvement_summaries.map((item) => `<tr><th>${esc(conditionLabel(item.condition))}</th><td>${item.individual_count}人／${item.group_count}组</td><td>${formatNumber(item.mean)}</td><td>${formatNumber(item.sd)}</td><td>${formatNumber(item.median)}</td><td>${item.improved_count}</td><td>${item.unchanged_count}</td><td>${item.worsened_count}</td><td>${formatNumber(item.improved_percentage)}%</td></tr>`).join('')
  const taskRows = report.task_summaries.map((task) => `<tr><th>${esc(taskLabel(task.task_id))}</th>${report.conditions.map((condition) => {
    const item = task.conditions.find((row) => row.condition === condition)
    return `<td>n=${item?.n ?? 0}; 平均改善=${formatNumber(item?.mean ?? null)}; SD=${formatNumber(item?.sd ?? null)}</td>`
  }).join('')}</tr>`).join('')
  const positionRows = report.member_position_summaries.map((position) => `<tr><th>${esc(positionLabel(position.position))}</th>${report.conditions.map((condition) => {
    const item = position.conditions.find((row) => row.condition === condition)
    return `<td>n=${item?.n ?? 0}; 平均改善=${formatNumber(item?.mean ?? null)}</td>`
  }).join('')}</tr>`).join('')
  const baselineCells = report.conditions.map((condition) => {
    const item = report.baseline_stats.find((row) => row.condition === condition)
    return `<td>个人 n=${item?.n ?? 0}; M=${formatNumber(item?.mean ?? null)}; SD=${formatNumber(item?.sd ?? null)}; Median=${formatNumber(item?.median ?? null)}</td>`
  }).join('')
  const withinRows = report.within_condition_tests.map((item) => {
    const conclusion = item.status !== 'ok' ? '数据不足' : item.significant ? (Number(item.mean_group_improvement) > 0 ? '显著改善' : '显著变差') : '未检出显著变化'
    return `<tr><th>${esc(conditionLabel(item.condition))}</th><td>${item.group_count}</td><td>${formatNumber(item.mean_group_improvement)}</td><td>${formatNumber(item.p_value)}</td><td>${formatNumber(item.p_value_adjusted)}</td><td>${formatNumber(item.effect_size)}</td><td>${conclusion}</td></tr>`
  }).join('')
  const pairRows = report.pairwise_tests.length
    ? report.pairwise_tests.map((item) => `<tr><td>${esc(conditionLabel(item.condition_a))}</td><td>${esc(conditionLabel(item.condition_b))}</td><td>${formatNumber(item.mean_difference)}</td><td>${formatNumber(item.p_value)}</td><td>${formatNumber(item.p_value_adjusted)}</td><td>${item.significant ? '是' : '否'}</td></tr>`).join('')
    : `<tr><td colspan="6">${report.conditions.length < 3 ? '当前模式无需三条件事后比较' : '总体检验未达到显著水平，不执行事后比较'}</td></tr>`
  const details = report.observations.map((item) => `<tr><td>${esc(conditionLabel(item.condition))}</td><td>${esc(taskLabel(item.task_id))}</td><td>${esc(item.group_id)}</td><td>${esc(item.participant_id)}</td><td>${formatNumber(item.individual_score)}</td><td>${formatNumber(item.group_score)}</td><td>${formatNumber(item.improvement)}</td><td>${esc(positionLabel(item.member_position))}</td></tr>`).join('')
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>个人到小组成绩变化分析报告</title><style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#172033;margin:32px;line-height:1.55}h1{margin-bottom:4px}h2{margin-top:28px}p.note{color:#526071;background:#f8fafc;padding:12px 14px;border-left:4px solid #2563eb}table{width:100%;border-collapse:collapse;margin:12px 0}th,td{border:1px solid #dbe3ee;padding:8px 10px;text-align:left;vertical-align:top}th{background:#f4f7fb}.ok{color:#047857}.warning{color:#b45309}@media print{body{margin:12mm}}
</style></head><body><h1>个人到小组成绩变化分析报告</h1><p>生成时间：${esc(new Date().toLocaleString('zh-CN'))}</p>
<p class="note"><strong>口径：</strong>改善值 = 个人独立分 IS − 小组最终分 GS。任务分数越低越好，因此正改善值表示小组共同答案优于该成员原答案，负值表示小组答案更差。这不是个人前测—个人后测，因为系统没有采集讨论后的个人独立答案。同组三人共享一个 GS，推断统计以小组为单位。</p>
<h2>样本</h2><table><tr><th>总个人数</th><td>${report.total_individuals}</td><th>总小组数</th><td>${report.total_groups}</td></tr>${report.conditions.map((condition) => `<tr><th>${esc(conditionLabel(condition))}</th><td>${report.individuals_by_condition[condition] ?? 0} 人</td><th>独立小组</th><td>${report.groups_by_condition[condition] ?? 0} 组</td></tr>`).join('')}</table>
<h2>个人到小组改善</h2><table><tr><th>条件</th><th>个人／小组n</th><th>平均改善</th><th>SD</th><th>Median</th><th>改善</th><th>不变</th><th>变差</th><th>改善比例</th></tr>${improvementRows}</table>
<h2>各条件内是否整体改善</h2><table><tr><th>条件</th><th>独立小组n</th><th>小组平均改善</th><th>原始p</th><th>Holm校正后p</th><th>Cohen's dz</th><th>结论</th></tr>${withinRows}</table><p class="note">每组先计算 AIS−GS，再以小组为独立单位执行双侧符号翻转置换检验。校正后 p&lt;.05 且平均改善为正，才报告为显著改善。</p>
<h2>按任务分层的改善值</h2><table><tr><th>任务</th>${conditionHeaders}</tr>${taskRows}</table>
<h2>不同起点成员的改善</h2><table><tr><th>组内位置</th>${conditionHeaders}</tr>${positionRows}</table><p class="note">每组按个人独立分由低到高确定原最佳、中间和最弱成员；并列时按参与者编码稳定排序。</p>
<h2>个人独立分基线</h2><table><tr><th>指标</th>${conditionHeaders}</tr><tr><th>个人 IS</th>${baselineCells}</tr></table>
<h2>AIS 一致性校验</h2><p class="${report.ais_consistency.status}">${esc(report.ais_consistency.note)}；核对 ${report.ais_consistency.checked_groups} 组，最大绝对差 ${formatNumber(report.ais_consistency.max_absolute_difference)}。</p>
<h2>平均改善值的条件检验</h2><table><tr><th>方法</th><th>统计量</th><th>p</th><th>效应量</th><th>状态</th></tr><tr><td>${esc(report.statistical_test.method)}</td><td>${esc(report.statistical_test.statistic_name)}=${formatNumber(report.statistical_test.statistic)}</td><td>${formatNumber(report.statistical_test.p_value)}</td><td>${esc(report.statistical_test.effect_size_name)}=${formatNumber(report.statistical_test.effect_size)}</td><td>${esc(report.statistical_test.status)}</td></tr></table><p class="note">${esc(report.statistical_test.note)}</p>
<h2>条件两两比较</h2><table><tr><th>条件A</th><th>条件B</th><th>平均改善差(B−A)</th><th>原始p</th><th>Holm校正后p</th><th>显著</th></tr>${pairRows}</table>
<h2>匿名配对明细</h2><table><tr><th>条件</th><th>任务</th><th>小组</th><th>参与者编码</th><th>个人IS</th><th>小组GS</th><th>改善IS−GS</th><th>原组内位置</th></tr>${details}</table></body></html>`
}
