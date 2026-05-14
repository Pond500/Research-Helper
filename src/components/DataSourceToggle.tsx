'use client';

import React, { useState, useRef } from 'react';
import { Upload, ChevronDown } from 'lucide-react';

interface DataSourceToggleProps {
  onSourcesChange: (sources: string[]) => void;
  activeSources?: string[];
}

const SOURCES = [
  { id: 'tavily', label: 'Tavily' },
  { id: 'searxng', label: 'SearxNG' },
  { id: 'qdrant', label: 'Local Knowledge' },
];

export function DataSourceToggle({ onSourcesChange, activeSources }: DataSourceToggleProps) {
  const [sources, setSources] = useState<string[]>(activeSources ?? ['tavily']);
  const [uploadText, setUploadText] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleToggle = (source: string) => {
    let next = sources.includes(source)
      ? sources.filter((s) => s !== source)
      : [...sources, source];
    if (next.length === 0) next = ['tavily'];
    setSources(next);
    onSourcesChange(next);
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setIsUploading(true);
    setUploadText(`Uploading ${file.name}…`);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch('/api/upload', { method: 'POST', body: formData });
      if (res.ok) {
        const data = await res.json();
        setUploadText(`✓ ${data.chunks_indexed} chunks indexed`);
        if (!sources.includes('qdrant')) handleToggle('qdrant');
      } else {
        setUploadText('Upload failed');
      }
    } catch {
      setUploadText('Upload error');
    }
    setIsUploading(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="px-4 py-2.5 border-b border-border/60 bg-background/80 backdrop-blur-sm">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-medium text-muted-foreground mr-1">Sources:</span>

        {SOURCES.map(({ id, label }) => {
          const active = sources.includes(id);
          return (
            <button
              key={id}
              onClick={() => handleToggle(id)}
              className={`px-2.5 py-1 rounded-full text-xs font-medium transition-all duration-150 border ${
                active
                  ? 'bg-primary text-primary-foreground border-primary shadow-sm'
                  : 'bg-background text-muted-foreground border-border hover:border-primary/50 hover:text-foreground'
              }`}
            >
              {label}
            </button>
          );
        })}

        {/* Upload toggle */}
        <button
          onClick={() => setShowUpload((v) => !v)}
          className="ml-auto flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border border-border text-muted-foreground hover:text-foreground hover:border-primary/50 transition-all duration-150"
        >
          <Upload className="w-3 h-3" />
          Upload doc
          <ChevronDown className={`w-3 h-3 transition-transform ${showUpload ? 'rotate-180' : ''}`} />
        </button>
      </div>

      {/* Upload panel */}
      {showUpload && (
        <div className="mt-2 flex items-center gap-3">
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="px-3 py-1 text-xs bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors font-medium"
          >
            {isUploading ? 'Uploading…' : 'Browse PDF / TXT / DOCX'}
          </button>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            accept=".pdf,.txt,.docx"
            className="hidden"
          />
          {uploadText && <span className="text-xs text-muted-foreground">{uploadText}</span>}
        </div>
      )}
    </div>
  );
}
