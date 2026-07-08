import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { LineChart, BarChart } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, MarkLineComponent, DataZoomComponent, LegendComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsCoreOption } from 'echarts/core';

echarts.use([
  LineChart, BarChart, GridComponent, TooltipComponent,
  MarkLineComponent, DataZoomComponent, LegendComponent, CanvasRenderer,
]);

export const CHART_COLORS = {
  gold: '#d4af6a',
  goldSoft: 'rgba(212,175,106,0.18)',
  up: '#e05d5d',
  down: '#4caf87',
  text: '#9aa1af',
  grid: '#232936',
};

export function Chart({ option, height = 280 }: { option: EChartsCoreOption; height?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    chartRef.current = echarts.init(ref.current);
    const onResize = () => chartRef.current?.resize();
    window.addEventListener('resize', onResize);
    return () => {
      window.removeEventListener('resize', onResize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option]);

  return <div ref={ref} style={{ width: '100%', height }} />;
}

export const baseAxis = {
  axisLine: { lineStyle: { color: CHART_COLORS.grid } },
  axisLabel: { color: CHART_COLORS.text, fontSize: 11 },
  splitLine: { lineStyle: { color: CHART_COLORS.grid, opacity: 0.5 } },
};

export const baseTooltip = {
  trigger: 'axis' as const,
  backgroundColor: '#1f2430',
  borderColor: '#313949',
  textStyle: { color: '#e8e6e1', fontSize: 12 },
};
