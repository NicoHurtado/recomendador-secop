// Registro mínimo de ECharts: solo lo que usan las gráficas.
// Se carga solo con las vistas que tienen gráficas.
import { use } from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'
import { BarChart, LineChart, ScatterChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, MarkLineComponent, MarkAreaComponent, MarkPointComponent, AriaComponent, LegendComponent } from 'echarts/components'
import { LegacyGridContainLabel, LabelLayout } from 'echarts/features'
import VChart from 'vue-echarts'

use([SVGRenderer, BarChart, LineChart, ScatterChart, GridComponent, TooltipComponent, MarkLineComponent, MarkAreaComponent, MarkPointComponent, AriaComponent, LegendComponent, LegacyGridContainLabel, LabelLayout])

export { VChart }
