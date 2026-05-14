export type Resource = {
  url: string;
  title: string;
  description: string;
  content?: string;
  resource_type: 'web' | 'tako_chart';
  card_id?: string;
  iframe_html?: string;
  source: string;
};

export type LogEntry = {
  message: string;
  done: boolean;
};

export type A2UIComponent = {
  type: 'stat_card' | 'kpi_row' | 'comparison_table' | 'data_grid' | 'timeline';
  title: string;
  data: Record<string, unknown>;
  source?: string;
};

export type ChartSpec = {
  id: string;
  title: string;
  option: Record<string, unknown>;
  source?: string;
};

export type Citation = {
  url: string;
  title: string;
  snippet: string;
};

export type AgentState = {
  model: string;
  research_question: string;
  report: string;
  search_sources?: string[];
  resources: Resource[];
  logs: LogEntry[];
  data_questions?: string[];
  pending_a2ui?: A2UIComponent[];
  charts?: ChartSpec[];
  suggested_questions?: string[];
  citations?: Record<string, Citation>;
}