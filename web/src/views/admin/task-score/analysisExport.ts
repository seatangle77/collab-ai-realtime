export type ReportLanguage = 'zh' | 'en'

export function downloadTextFile(content: string, filename: string, type: string) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? '' : String(value)
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function buildCsv(rows: unknown[][]): string {
  return `\uFEFF${rows.map((row) => row.map(csvCell).join(',')).join('\r\n')}`
}

export function serializeSvgElement(svg: SVGElement): string {
  const clone = svg.cloneNode(true) as SVGElement
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  const sourceNodes = [svg, ...Array.from(svg.querySelectorAll<SVGElement>('*'))]
  const cloneNodes = [clone, ...Array.from(clone.querySelectorAll<SVGElement>('*'))]
  const properties = ['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'opacity', 'font-family', 'font-size', 'font-weight', 'paint-order', 'text-rendering']
  sourceNodes.forEach((sourceNode, index) => {
    const targetNode = cloneNodes[index]
    if (!targetNode) return
    const computed = window.getComputedStyle(sourceNode)
    for (const property of properties) {
      const value = computed.getPropertyValue(property)
      if (value) targetNode.style.setProperty(property, value)
    }
  })
  return new XMLSerializer().serializeToString(clone)
}

export function downloadSvgElement(svg: SVGElement, filename: string) {
  const source = `<?xml version="1.0" encoding="UTF-8"?>\n${serializeSvgElement(svg)}`
  downloadTextFile(source, filename, 'image/svg+xml;charset=utf-8')
}

export const INTERACTIVE_CHART_CSS = `
  .interactive-chart{position:relative;margin:12px 0 20px;padding:12px;border:1px solid #d1d5db;border-radius:10px;background:#fff;page-break-inside:avoid}
  .interactive-chart h3{margin:0 0 8px}.interactive-chart svg{display:block;width:100%;height:auto;cursor:zoom-in}
  .chart-actions{display:flex;justify-content:flex-end;gap:8px;margin-bottom:8px}
  .chart-actions button,.chart-modal button{padding:7px 11px;border:1px solid #cbd5e1;border-radius:6px;background:#fff;color:#334155;font:600 12px inherit;cursor:pointer}
  .chart-actions button:hover,.chart-modal button:hover{background:#eff6ff;border-color:#93c5fd;color:#1d4ed8}
  .chart-modal{position:fixed;inset:0;z-index:9999;display:none;background:rgba(15,23,42,.88);padding:24px;overflow:auto}
  .chart-modal.open{display:flex;flex-direction:column}.chart-modal-toolbar{position:sticky;top:0;z-index:2;display:flex;justify-content:flex-end;gap:8px;padding:8px;background:rgba(15,23,42,.86)}
  .chart-modal-stage{min-width:1400px;margin:auto;padding:24px;background:#fff;border-radius:12px}.chart-modal-stage svg{display:block;width:100%;height:auto}
  @media print{.chart-actions,.chart-modal{display:none!important}}
`

export const INTERACTIVE_CHART_SCRIPT = `
  <script>
  (function(){
    function svgSource(svg){
      var copy=svg.cloneNode(true);copy.setAttribute('xmlns','http://www.w3.org/2000/svg');
      return '<?xml version="1.0" encoding="UTF-8"?>\\n'+new XMLSerializer().serializeToString(copy);
    }
    function download(svg,name){
      var blob=new Blob([svgSource(svg)],{type:'image/svg+xml;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');
      a.href=url;a.download=name;a.click();setTimeout(function(){URL.revokeObjectURL(url)},0);
    }
    document.querySelectorAll('figure svg').forEach(function(svg,index){
      if(svg.closest('.interactive-chart'))return;
      svg.style.cursor='zoom-in';svg.dataset.reportChart=String(index+1);
      var actions=document.createElement('div');actions.className='chart-actions';actions.innerHTML='<button type="button" data-chart-action="zoom">Enlarge</button><button type="button" data-chart-action="download" data-filename="chart-'+(index+1)+'.svg">Download SVG</button>';
      svg.parentNode.insertBefore(actions,svg);
    });
    document.addEventListener('click',function(event){
      var target=event.target.closest('[data-chart-action],.interactive-chart svg,figure svg');if(!target)return;
      var card=target.closest('.interactive-chart')||target.parentElement,svg=target.tagName&&target.tagName.toLowerCase()==='svg'?target:card&&card.querySelector('svg');if(!svg)return;
      if(target.dataset.chartAction==='download'){download(svg,target.dataset.filename||'chart.svg');return;}
      var modal=document.querySelector('.chart-modal');modal.querySelector('.chart-modal-stage').innerHTML=svg.outerHTML;modal.classList.add('open');document.body.style.overflow='hidden';
    });
    document.addEventListener('click',function(event){
      if(event.target.closest('[data-close-chart]')||event.target.classList.contains('chart-modal')){var modal=document.querySelector('.chart-modal');modal.classList.remove('open');modal.querySelector('.chart-modal-stage').innerHTML='';document.body.style.overflow='';}
    });
    document.addEventListener('keydown',function(event){if(event.key==='Escape'){var close=document.querySelector('[data-close-chart]');if(close)close.click();}});
  })();
  <\/script>
`

export function interactiveChartHtml(svg: string, title: string, filename: string, language: ReportLanguage): string {
  const zoom = language === 'zh' ? '放大查看' : 'Enlarge'
  const download = language === 'zh' ? '下载 SVG' : 'Download SVG'
  return `<section class="interactive-chart"><h3>${title}</h3><div class="chart-actions"><button type="button" data-chart-action="zoom">${zoom}</button><button type="button" data-chart-action="download" data-filename="${filename}">${download}</button></div>${svg}</section>`
}

export function chartModalHtml(language: ReportLanguage): string {
  return `<div class="chart-modal" role="dialog" aria-modal="true"><div class="chart-modal-toolbar"><button type="button" data-close-chart>${language === 'zh' ? '关闭' : 'Close'}</button></div><div class="chart-modal-stage"></div></div>`
}
