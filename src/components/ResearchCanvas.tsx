'use client';

import { useState, useRef, useEffect } from 'react';
import { Textarea } from '@/components/ui/textarea';
import { EditResourceDialog } from './EditResourceDialog';
import { AddResourceDialog } from './AddResourceDialog';
import { AgentState, Resource, ChartSpec } from '@/lib/types';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { MarkdownRenderer } from './MarkdownRenderer';
import { A2UIRenderer } from './A2UIRenderer';
import EChartsViewer from './EChartsViewer';
import { LiveActivityFeed } from './LiveActivityFeed';
import {
  LayoutDashboard,
  BookOpen,
  FileText,
  BarChart2,
  Trash2,
  ExternalLink,
  BarChart3,
  Sparkles,
  X,
} from 'lucide-react';

type Tab = 'overview' | 'sources' | 'report' | 'data';

type ResearchCanvasProps = {
  agentState: AgentState;
  isRunning: boolean;
  currentStep?: string;
  onStateUpdate: (updates: Partial<AgentState>) => void;
};

export function ResearchCanvas({
  agentState,
  isRunning,
  currentStep,
  onStateUpdate,
}: ResearchCanvasProps) {
  const [activeTab, setActiveTab] = useState<Tab>('overview');
  const [isViewMode, setIsViewMode] = useState(true);
  const [selectedChart, setSelectedChart] = useState<Resource | null>(null);
  const [editResource, setEditResource] = useState<Resource | null>(null);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [isEditResourceOpen, setIsEditResourceOpen] = useState(false);
  const [isAddResourceOpen, setIsAddResourceOpen] = useState(false);
  const [newResource, setNewResource] = useState<Resource>({
    url: '', title: '', description: '', resource_type: 'web', source: 'Manual',
  });

  /* Persist last known good state to prevent flicker */
  const lastResourcesRef = useRef<Resource[]>([]);
  const lastReportRef = useRef<string>('');
  const lastQuestionRef = useRef<string>('');

  if (agentState.resources?.length > 0) lastResourcesRef.current = agentState.resources;
  if (agentState.report?.length > 0) lastReportRef.current = agentState.report;
  if (agentState.research_question?.length > 0) lastQuestionRef.current = agentState.research_question;

  const resources = agentState.resources?.length > 0 ? agentState.resources : lastResourcesRef.current;
  const report = agentState.report?.length > 0 ? agentState.report : lastReportRef.current;
  const researchQuestion = agentState.research_question?.length > 0
    ? agentState.research_question : lastQuestionRef.current;
  const logs = agentState.logs ?? [];
  const a2uiComponents = agentState.pending_a2ui ?? [];
  const charts = agentState.charts ?? [];

  // Persist charts to avoid flicker
  const lastChartsRef = useRef<ChartSpec[]>([]);
  if (charts.length > 0) lastChartsRef.current = charts;
  const stableCharts = charts.length > 0 ? charts : lastChartsRef.current;

  // Auto-switch to Data tab when new components / charts arrive
  const prevA2UICountRef = useRef(0);
  const prevChartsCountRef = useRef(0);
  useEffect(() => {
    const newA2UI = a2uiComponents.length > prevA2UICountRef.current;
    const newCharts = stableCharts.length > prevChartsCountRef.current;
    if ((newA2UI || newCharts) && activeTab === 'overview') {
      setActiveTab('data');
    }
    prevA2UICountRef.current = a2uiComponents.length;
    prevChartsCountRef.current = stableCharts.length;
  }, [a2uiComponents.length, stableCharts.length, activeTab]);

  const clearA2UIComponents = () => onStateUpdate({ pending_a2ui: [] });

  const setResources = (r: Resource[]) => onStateUpdate({ resources: r });

  const addResource = () => {
    if (newResource.url) {
      setResources([...resources, { ...newResource }]);
      setNewResource({ url: '', title: '', description: '', resource_type: 'web', source: 'Manual' });
      setIsAddResourceOpen(false);
    }
  };

  const removeResource = (url: string) =>
    setResources(resources.filter((r) => r.url !== url));

  const handleCardClick = (resource: Resource) => {
    if (resource.resource_type === 'tako_chart') {
      setSelectedChart(resource);
    } else {
      setEditResource({ ...resource });
      setOriginalUrl(resource.url);
      setIsEditResourceOpen(true);
    }
  };

  const updateResource = () => {
    if (editResource && originalUrl) {
      setResources(resources.map((r) => (r.url === originalUrl ? { ...editResource } : r)));
      setEditResource(null);
      setOriginalUrl(null);
      setIsEditResourceOpen(false);
    }
  };

  const showActivity = isRunning || logs.length > 0;
  const webResources = resources.filter((r) => r.resource_type === 'web');
  const chartResources = resources.filter((r) => r.resource_type === 'tako_chart');

  const TABS: { id: Tab; icon: React.ReactNode; label: string; badge?: number }[] = [
    { id: 'overview', icon: <LayoutDashboard className="w-3.5 h-3.5" />, label: 'Overview' },
    { id: 'sources', icon: <BookOpen className="w-3.5 h-3.5" />, label: 'Sources', badge: resources.length || undefined },
    { id: 'report', icon: <FileText className="w-3.5 h-3.5" />, label: 'Report' },
    { id: 'data', icon: <BarChart2 className="w-3.5 h-3.5" />, label: 'Data', badge: (a2uiComponents.length + stableCharts.length) || undefined },
  ];

  return (
    <div className="h-full flex flex-col overflow-hidden bg-background">
      {/* Tab navigation */}
      <div className="flex items-center border-b border-border bg-card px-4 flex-shrink-0">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`relative flex items-center gap-1.5 px-3 py-3.5 text-xs font-medium transition-colors ${
              activeTab === tab.id
                ? 'text-primary'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {tab.icon}
            {tab.label}
            {tab.badge !== undefined && (
              <span className="ml-0.5 px-1.5 py-0.5 text-[10px] rounded-full bg-primary/10 text-primary font-semibold">
                {tab.badge}
              </span>
            )}
            {activeTab === tab.id && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary rounded-full" />
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto">

        {/* ─── OVERVIEW ─── */}
        {activeTab === 'overview' && (
          <div className="p-6 space-y-5">
            {showActivity && (
              <LiveActivityFeed logs={logs} isRunning={isRunning} currentStep={currentStep} />
            )}

            {/* Research Question */}
            <div>
              <h2 className="font-display text-base font-semibold text-foreground mb-2">
                Research Question
              </h2>
              <div className="bg-card rounded-2xl border border-border px-5 py-4 min-h-[56px] flex items-center">
                {researchQuestion ? (
                  <p className="text-sm text-foreground leading-relaxed">{researchQuestion}</p>
                ) : (
                  <p className="text-sm text-muted-foreground italic">
                    The agent will identify your research question automatically…
                  </p>
                )}
              </div>
            </div>

            {/* Quick source preview */}
            {resources.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h2 className="font-display text-base font-semibold text-foreground">
                    Sources{' '}
                    <span className="font-sans text-xs font-normal text-muted-foreground">
                      ({resources.length})
                    </span>
                  </h2>
                  <button
                    onClick={() => setActiveTab('sources')}
                    className="text-xs text-primary hover:underline"
                  >
                    View all →
                  </button>
                </div>
                <div className="grid grid-cols-1 gap-2">
                  {resources.slice(0, 3).map((r, i) => (
                    <SourceCard
                      key={i}
                      resource={r}
                      onClick={() => handleCardClick(r)}
                      onRemove={() => removeResource(r.url)}
                    />
                  ))}
                  {resources.length > 3 && (
                    <button
                      onClick={() => setActiveTab('sources')}
                      className="text-xs text-muted-foreground hover:text-primary py-1 transition-colors text-left"
                    >
                      +{resources.length - 3} more sources
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Report preview */}
            {report && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h2 className="font-display text-base font-semibold text-foreground">
                    Report Preview
                  </h2>
                  <button
                    onClick={() => setActiveTab('report')}
                    className="text-xs text-primary hover:underline"
                  >
                    Full report →
                  </button>
                </div>
                <div className="bg-card rounded-2xl border border-border px-5 py-4 text-sm text-muted-foreground line-clamp-4 leading-relaxed">
                  {report.replace(/[#*`]/g, '').slice(0, 300)}…
                </div>
              </div>
            )}

            {/* Data components preview */}
            {a2uiComponents.length > 0 && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h2 className="font-display text-base font-semibold text-foreground flex items-center gap-1.5">
                    Data Components
                    <span className="font-sans text-xs font-normal text-muted-foreground">
                      ({a2uiComponents.length})
                    </span>
                  </h2>
                  <button
                    onClick={() => setActiveTab('data')}
                    className="text-xs text-primary hover:underline"
                  >
                    View all →
                  </button>
                </div>
                {/* Preview of first component summary */}
                <div className="space-y-2">
                  {a2uiComponents.slice(0, 2).map((c, i) => (
                    <button
                      key={i}
                      onClick={() => setActiveTab('data')}
                      className="w-full flex items-center gap-3 bg-card border border-border rounded-2xl px-4 py-3 hover:border-primary/30 hover:shadow-sm transition-all text-left"
                    >
                      <div className="w-8 h-8 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                        <Sparkles className="w-4 h-4 text-primary" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground truncate">{c.title}</p>
                        <p className="text-xs text-muted-foreground capitalize">{c.type.replace('_', ' ')}</p>
                      </div>
                    </button>
                  ))}
                  {a2uiComponents.length > 2 && (
                    <button
                      onClick={() => setActiveTab('data')}
                      className="text-xs text-muted-foreground hover:text-primary py-1 transition-colors text-left"
                    >
                      +{a2uiComponents.length - 2} more components
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ─── SOURCES ─── */}
        {activeTab === 'sources' && (
          <div className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-display text-base font-semibold text-foreground">
                Research Sources
                {resources.length > 0 && (
                  <span className="font-sans text-xs font-normal text-muted-foreground ml-1">
                    ({resources.length})
                  </span>
                )}
              </h2>
              <div className="flex items-center gap-2">
                <EditResourceDialog
                  isOpen={isEditResourceOpen}
                  onOpenChange={setIsEditResourceOpen}
                  editResource={editResource}
                  setEditResource={setEditResource}
                  updateResource={updateResource}
                />
                <AddResourceDialog
                  isOpen={isAddResourceOpen}
                  onOpenChange={setIsAddResourceOpen}
                  newResource={newResource}
                  setNewResource={setNewResource}
                  addResource={addResource}
                />
              </div>
            </div>

            {resources.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-center">
                <div className="w-12 h-12 rounded-2xl bg-secondary flex items-center justify-center mb-3">
                  <BookOpen className="w-5 h-5 text-muted-foreground" />
                </div>
                <p className="text-sm text-muted-foreground">No sources yet.</p>
                <p className="text-xs text-muted-foreground mt-1">
                  Run a research query or add sources manually.
                </p>
              </div>
            ) : (
              <div className="space-y-5">
                {chartResources.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-2">
                      Charts ({chartResources.length})
                    </h3>
                    <div className="grid grid-cols-1 gap-2">
                      {chartResources.map((r, i) => (
                        <SourceCard
                          key={i}
                          resource={r}
                          onClick={() => handleCardClick(r)}
                          onRemove={() => removeResource(r.url)}
                        />
                      ))}
                    </div>
                  </div>
                )}
                {webResources.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-2">
                      Web Sources ({webResources.length})
                    </h3>
                    <div className="grid grid-cols-1 gap-2">
                      {webResources.map((r, i) => (
                        <SourceCard
                          key={i}
                          resource={r}
                          onClick={() => handleCardClick(r)}
                          onRemove={() => removeResource(r.url)}
                        />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ─── REPORT ─── */}
        {activeTab === 'report' && (
          <div className="p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-base font-semibold text-foreground">
                Research Draft
              </h2>
              <div className="flex items-center gap-1 bg-secondary rounded-xl p-1">
                <button
                  onClick={() => setIsViewMode(true)}
                  className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                    isViewMode
                      ? 'bg-card text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  Preview
                </button>
                <button
                  onClick={() => setIsViewMode(false)}
                  className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
                    !isViewMode
                      ? 'bg-card text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  Edit
                </button>
              </div>
            </div>

            {isViewMode ? (
              report ? (
                <MarkdownRenderer content={report} charts={stableCharts} citations={agentState.citations} />
              ) : (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="w-12 h-12 rounded-2xl bg-secondary flex items-center justify-center mb-3">
                    <FileText className="w-5 h-5 text-muted-foreground" />
                  </div>
                  <p className="text-sm text-muted-foreground">No report yet.</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Ask the agent to research a topic.
                  </p>
                </div>
              )
            ) : (
              <Textarea
                data-test-id="research-draft"
                placeholder="Write your research draft here…"
                value={report || ''}
                onChange={(e) => onStateUpdate({ report: e.target.value })}
                rows={20}
                aria-label="Research draft"
                className="bg-card border-border rounded-2xl text-sm font-normal focus-visible:ring-primary/30 placeholder:text-muted-foreground resize-none"
              />
            )}
          </div>
        )}

        {/* ─── DATA ─── */}
        {activeTab === 'data' && (
          <div className="p-6 space-y-6">
            {/* Charts section */}
            {stableCharts.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-3">
                  Charts ({stableCharts.length})
                </h3>
                <div className="space-y-2">
                  {stableCharts.map((chart) => (
                    <EChartsViewer key={chart.id} chart={chart} />
                  ))}
                </div>
              </div>
            )}

            {/* A2UI section */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest">
                  {a2uiComponents.length > 0 ? `Structured Data (${a2uiComponents.length})` : 'Structured Data'}
                </h3>
                {a2uiComponents.length > 0 && (
                  <button
                    onClick={clearA2UIComponents}
                    className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-destructive transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                    Clear
                  </button>
                )}
              </div>
              {a2uiComponents.length === 0 && stableCharts.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="w-12 h-12 rounded-2xl bg-secondary flex items-center justify-center mb-3">
                    <BarChart2 className="w-5 h-5 text-muted-foreground" />
                  </div>
                  <p className="text-sm text-muted-foreground">No data yet.</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    The agent will generate charts and structured data here.
                  </p>
                </div>
              ) : a2uiComponents.length > 0 ? (
                <A2UIRenderer components={a2uiComponents} />
              ) : null}
            </div>
          </div>
        )}
      </div>

      {/* Chart preview modal */}
      <Dialog
        open={selectedChart !== null}
        onOpenChange={(open) => !open && setSelectedChart(null)}
      >
        <DialogContent className="max-w-4xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-display">{selectedChart?.title}</DialogTitle>
          </DialogHeader>
          {selectedChart?.iframe_html ? (
            <div
              className="w-full min-h-[500px]"
              dangerouslySetInnerHTML={{ __html: selectedChart.iframe_html }}
            />
          ) : (
            <div className="p-8 text-center text-muted-foreground">
              Chart preview not available
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

/* ─── SourceCard sub-component ─── */
function SourceCard({
  resource,
  onClick,
  onRemove,
}: {
  resource: Resource;
  onClick: () => void;
  onRemove: () => void;
}) {
  const isChart = resource.resource_type === 'tako_chart';
  let domain = '';
  try {
    domain = new URL(resource.url).hostname.replace('www.', '');
  } catch {
    domain = resource.url;
  }

  return (
    <div
      onClick={onClick}
      className="group flex items-start gap-3 bg-card border border-border rounded-2xl px-4 py-3 hover:border-primary/30 hover:shadow-sm transition-all duration-150 cursor-pointer"
    >
      {/* Icon */}
      <div className="flex-shrink-0 mt-0.5">
        {isChart ? (
          <div className="w-8 h-8 rounded-xl bg-blue-50 border border-blue-100 flex items-center justify-center">
            <BarChart3 className="w-4 h-4 text-blue-500" />
          </div>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={`https://www.google.com/s2/favicons?domain=${resource.url}&sz=32`}
            alt=""
            className="w-8 h-8 rounded-xl border border-border object-contain bg-secondary p-1"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
            }}
          />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          {isChart ? (
            <span className="text-[10px] font-semibold text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded-md border border-blue-100">
              Chart
            </span>
          ) : (
            <span className="text-[10px] text-muted-foreground truncate">{domain}</span>
          )}
          {resource.source && resource.source !== 'Manual' && (
            <span className="text-[10px] text-muted-foreground/60">{resource.source}</span>
          )}
        </div>
        <p className="text-sm font-medium text-foreground truncate leading-snug">
          {resource.title || domain}
        </p>
        {resource.description && (
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2 leading-relaxed">
            {resource.description}
          </p>
        )}
      </div>

      {/* Actions — visible on hover */}
      <div className="flex-shrink-0 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        {!isChart && (
          <a
            href={resource.url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:text-primary hover:bg-accent transition-colors"
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}
        <button
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="w-7 h-7 rounded-lg flex items-center justify-center text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
          aria-label="Remove source"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
