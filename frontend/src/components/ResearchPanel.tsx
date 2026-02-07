import { useMemo, useState } from 'react';
import { Copy, Sparkles } from 'lucide-react';
import toast from 'react-hot-toast';
import { merlinApi } from '../services/api';
import { ResearchResponse } from '../types';

type ResearchPanelProps = {
  apiUrl?: string;
};

const parseList = (value: string) => {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
};

const splitSnippets = (value: string) => {
  const trimmed = value.trim();
  if (!trimmed) return [] as string[];
  if (trimmed.includes('\n---\n')) {
    return trimmed
      .split('\n---\n')
      .map((snippet) => snippet.trim())
      .filter(Boolean);
  }
  return [trimmed];
};

export default function ResearchPanel({ apiUrl }: ResearchPanelProps) {
  const baseUrl = useMemo(() => apiUrl || 'http://localhost:8000', [apiUrl]);
  const [query, setQuery] = useState('');
  const [imagePaths, setImagePaths] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [stagedPaths, setStagedPaths] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [codeSnippets, setCodeSnippets] = useState('');
  const [includeWebSearch, setIncludeWebSearch] = useState(true);
  const [includeCodeAnalysis, setIncludeCodeAnalysis] = useState(false);
  const [useLocalVision, setUseLocalVision] = useState(false);
  const [storeToKnowledge, setStoreToKnowledge] = useState(false);
  const [outputFormat, setOutputFormat] = useState<'markdown' | 'json'>('markdown');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ResearchResponse | null>(null);

  const runResearch = async () => {
    if (!query.trim()) {
      toast.error('Enter a research query');
      return;
    }

    try {
      setLoading(true);
      merlinApi.setBaseUrl(baseUrl);
      const payload = {
        query: query.trim(),
        include_web_search: includeWebSearch,
        include_code_analysis: includeCodeAnalysis,
        image_paths: [...parseList(imagePaths), ...stagedPaths],
        code_snippets: splitSnippets(codeSnippets),
        output_format: outputFormat,
        use_local_vision: useLocalVision,
        store_to_knowledge: storeToKnowledge,
        metadata: { requested_by: 'MerlinDashboard' },
      };
      const response = await merlinApi.runResearchHttp(payload);
      setResult(response);
      toast.success('Research report ready');
    } catch (error) {
      console.error('Research failed:', error);
      toast.error('Research failed');
    } finally {
      setLoading(false);
    }
  };

  const uploadImages = async () => {
    if (selectedFiles.length === 0) {
      toast.error('Select one or more images to upload');
      return;
    }
    try {
      setUploading(true);
      merlinApi.setBaseUrl(baseUrl);
      const uploaded: string[] = [];

      for (const file of selectedFiles) {
        const base64 = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => {
            const result = reader.result?.toString() || '';
            const parts = result.split(',');
            resolve(parts.length > 1 ? parts[1] : result);
          };
          reader.onerror = () => reject(new Error('Failed to read file'));
          reader.readAsDataURL(file);
        });

        const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, '_');
        const path = `artifacts/research_uploads/${Date.now()}_${safeName}`;
        await merlinApi.writeFileBase64(path, base64, true);
        uploaded.push(path);
      }

      setStagedPaths((prev) => [...prev, ...uploaded]);
      setSelectedFiles([]);
      toast.success(`Uploaded ${uploaded.length} image(s)`);
    } catch (error) {
      console.error('Upload failed:', error);
      toast.error('Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const copyReport = async () => {
    if (!result?.formatted) {
      return;
    }
    try {
      await navigator.clipboard.writeText(result.formatted);
      toast.success('Report copied');
    } catch (error) {
      console.error('Copy failed:', error);
      toast.error('Copy failed');
    }
  };

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-merlin-blue" />
          <h3 className="text-lg font-semibold">Multi-Modal Research</h3>
        </div>
        <button
          onClick={runResearch}
          className="btn btn-primary"
          disabled={loading}
        >
          {loading ? 'Running…' : 'Run Research'}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-3">
          <div>
            <label className="text-xs text-dark-muted">Query</label>
            <textarea
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="What do you want to investigate?"
              className="w-full mt-1 rounded-md bg-dark-border border border-dark-border px-3 py-2 text-sm text-dark-text"
              rows={3}
            />
          </div>
          <div>
            <label className="text-xs text-dark-muted">Image paths (server-side)</label>
            <input
              value={imagePaths}
              onChange={(event) => setImagePaths(event.target.value)}
              placeholder="C:\\path\\to\\image.png, /var/data/image.jpg"
              className="w-full mt-1 rounded-md bg-dark-border border border-dark-border px-3 py-2 text-sm text-dark-text"
            />
          </div>
          <div>
            <label className="text-xs text-dark-muted">Upload images</label>
            <div className="mt-2 flex flex-col gap-2">
              <input
                type="file"
                accept="image/*"
                multiple
                onChange={(event) =>
                  setSelectedFiles(Array.from(event.target.files || []))
                }
              />
              <div className="flex items-center gap-2">
                <button
                  onClick={uploadImages}
                  className="btn btn-secondary"
                  disabled={uploading || selectedFiles.length === 0}
                >
                  {uploading ? 'Uploading…' : 'Upload Images'}
                </button>
                {stagedPaths.length > 0 && (
                  <span className="text-xs text-dark-muted">
                    {stagedPaths.length} staged
                  </span>
                )}
              </div>
              {stagedPaths.length > 0 && (
                <div className="text-[10px] text-dark-muted break-all">
                  {stagedPaths.join(', ')}
                </div>
              )}
            </div>
          </div>
          <div>
            <label className="text-xs text-dark-muted">Code snippets (use --- to separate)</label>
            <textarea
              value={codeSnippets}
              onChange={(event) => setCodeSnippets(event.target.value)}
              placeholder="print('analysis')\n---\nSELECT * FROM table;"
              className="w-full mt-1 rounded-md bg-dark-border border border-dark-border px-3 py-2 text-sm text-dark-text"
              rows={4}
            />
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-xs text-dark-muted">Output format</label>
            <select
              value={outputFormat}
              onChange={(event) => setOutputFormat(event.target.value as 'markdown' | 'json')}
              className="w-full mt-1 rounded-md bg-dark-border border border-dark-border px-3 py-2 text-sm text-dark-text"
            >
              <option value="markdown">Markdown</option>
              <option value="json">JSON</option>
            </select>
          </div>
          <div className="space-y-2">
            <label className="text-xs text-dark-muted">Options</label>
            <div className="flex items-center justify-between text-sm text-dark-text">
              <span>Web search</span>
              <input
                type="checkbox"
                checked={includeWebSearch}
                onChange={(event) => setIncludeWebSearch(event.target.checked)}
              />
            </div>
            <div className="flex items-center justify-between text-sm text-dark-text">
              <span>Code analysis</span>
              <input
                type="checkbox"
                checked={includeCodeAnalysis}
                onChange={(event) => setIncludeCodeAnalysis(event.target.checked)}
              />
            </div>
            <div className="flex items-center justify-between text-sm text-dark-text">
              <span>Local vision</span>
              <input
                type="checkbox"
                checked={useLocalVision}
                onChange={(event) => setUseLocalVision(event.target.checked)}
              />
            </div>
            <div className="flex items-center justify-between text-sm text-dark-text">
              <span>Store to knowledge</span>
              <input
                type="checkbox"
                checked={storeToKnowledge}
                onChange={(event) => setStoreToKnowledge(event.target.checked)}
              />
            </div>
          </div>
          {result?.report && (
            <div className="rounded-md border border-dark-border p-3 text-xs text-dark-muted">
              <div>Sources: {result.report.sources.length}</div>
              <div>Images analyzed: {result.report.images_analyzed}</div>
              <div>Confidence: {(result.report.confidence * 100).toFixed(1)}%</div>
            </div>
          )}
        </div>
      </div>

      {result?.formatted && (
        <div className="mt-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs text-dark-muted">Report</span>
            <button
              onClick={copyReport}
              className="text-xs text-dark-muted hover:text-dark-text inline-flex items-center gap-1"
            >
              <Copy className="w-3 h-3" />
              Copy
            </button>
          </div>
          <pre className="max-h-72 overflow-auto rounded-md bg-dark-border border border-dark-border p-3 text-xs text-dark-text whitespace-pre-wrap">
            {result.formatted}
          </pre>
        </div>
      )}
    </div>
  );
}
