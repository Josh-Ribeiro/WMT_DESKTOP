import { useEffect, useRef, useState } from 'react';
import { renderAsync } from 'docx-preview';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Sidebar } from '@/components/Sidebar';
import { useApi } from '@/hooks/useApi';
import { useAuth } from '@/hooks/useAuth';
import { API_BASE_URL, getStoredToken } from '@/lib/api';
import { CheckCircle2, Download, FileText, Laptop, Loader2, Printer, UserRound } from 'lucide-react';
import { toast } from 'sonner';
import { useLocation } from 'wouter';

interface TermType {
  value: 'responsibility' | 'return';
  label: string;
  template_path: string;
  template_accessible: boolean;
}

interface TermsConfig {
  types: TermType[];
  placeholders: string[];
}

interface GeneratedDocument {
  url: string;
  filename: string;
  blob: Blob;
}

function fileNameFromDisposition(disposition: string | null, fallback: string) {
  const match = (disposition || '').match(/filename="?([^";]+)"?/i);
  return match?.[1] || fallback;
}

function downloadDocument(document: GeneratedDocument) {
  const link = window.document.createElement('a');
  link.href = document.url;
  link.download = document.filename;
  window.document.body.appendChild(link);
  link.click();
  link.remove();
}

export default function Terms() {
  const { user, logout, loading: authLoading } = useAuth();
  const [, navigate] = useLocation();
  const [wk, setWk] = useState('');
  const [employeeName, setEmployeeName] = useState('');
  const [termType, setTermType] = useState<'responsibility' | 'return'>('responsibility');
  const [generating, setGenerating] = useState(false);
  const [printing, setPrinting] = useState(false);
  const [status, setStatus] = useState('Fill in the workstation and generate the document directly.');
  const [generatedDocument, setGeneratedDocument] = useState<GeneratedDocument | null>(null);
  const [printPreview, setPrintPreview] = useState<GeneratedDocument | null>(null);
  const [printWhenReady, setPrintWhenReady] = useState(false);
  const [previewRendering, setPreviewRendering] = useState(false);
  const previewContainerRef = useRef<HTMLDivElement | null>(null);
  const previewStyleRef = useRef<HTMLDivElement | null>(null);

  const { data: config } = useApi<TermsConfig>('/api/terms/config', {
    skip: authLoading || !user,
  });

  const selectedType = config?.types.find((type) => type.value === termType);

  useEffect(() => {
    return () => {
      if (generatedDocument) {
        URL.revokeObjectURL(generatedDocument.url);
      }
    };
  }, [generatedDocument]);

  useEffect(() => {
    return () => {
      if (printPreview) {
        URL.revokeObjectURL(printPreview.url);
      }
    };
  }, [printPreview]);

  useEffect(() => {
    const container = previewContainerRef.current;
    const styleContainer = previewStyleRef.current;
    if (!printPreview || !container || !styleContainer) {
      return;
    }

    let cancelled = false;
    container.innerHTML = '';
    styleContainer.innerHTML = '';
    setPreviewRendering(true);

    renderAsync(printPreview.blob, container, styleContainer, {
      className: 'wmt-docx-preview',
      ignoreFonts: false,
      ignoreHeight: false,
      ignoreWidth: false,
      inWrapper: true,
      renderFooters: true,
      renderHeaders: true,
      useBase64URL: true,
    })
      .then(() => {
        if (cancelled) {
          return;
        }
        container.contentEditable = 'true';
        container.spellcheck = false;
        container.querySelectorAll<HTMLElement>('.wmt-docx-preview-wrapper, .wmt-docx-preview, section').forEach((element) => {
          element.contentEditable = 'true';
        });
        setPreviewRendering(false);
        if (printWhenReady) {
          setPrintWhenReady(false);
          window.setTimeout(() => handlePrintPreview(), 250);
        }
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        setPreviewRendering(false);
        const message = error instanceof Error ? error.message : 'Failed to render DOCX preview.';
        setStatus(message);
        toast.error(message);
      });

    return () => {
      cancelled = true;
    };
  }, [printPreview, printWhenReady]);

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  const handleDownloadAgain = () => {
    if (!generatedDocument) {
      return;
    }

    downloadDocument(generatedDocument);
  };

  const handleOpenForPrint = async () => {
    const target = wk.trim();
    if (!target) {
      toast.error('Enter a workstation first.');
      return;
    }

    setPrinting(true);
    setStatus('Preparing print preview...');
    setPrintPreview((current) => {
      if (current) {
        URL.revokeObjectURL(current.url);
      }
      return null;
    });
    try {
      const token = getStoredToken();
      const response = await fetch(`${API_BASE_URL}/api/terms/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          wk: target,
          employee_name: employeeName.trim(),
          term_type: termType,
        }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || 'Failed to prepare print preview.');
      }

      const blob = await response.blob();
      const filename = fileNameFromDisposition(
        response.headers.get('Content-Disposition'),
        `${target}-${termType}.docx`
      );
      const document = { url: URL.createObjectURL(blob), filename, blob };
      const previewDocument = { url: URL.createObjectURL(blob), filename, blob };
      setGeneratedDocument((current) => {
        if (current) {
          URL.revokeObjectURL(current.url);
        }
        return document;
      });
      setPrintPreview(previewDocument);
      setPrintWhenReady(false);
      setStatus('Print preview ready.');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to prepare print preview.';
      setStatus(message);
      toast.error(message);
    } finally {
      setPrinting(false);
    }
  };

  const handleClosePreview = () => {
    setPrintWhenReady(false);
    setPrintPreview((current) => {
      if (current) {
        URL.revokeObjectURL(current.url);
      }
      return null;
    });
  };

  const handlePrintPreview = () => {
    const container = previewContainerRef.current;
    const styleContainer = previewStyleRef.current;
    if (!container || !styleContainer || !container.innerHTML.trim() || previewRendering) {
      toast.error('Print preview is not ready yet.');
      return;
    }

    const frame = window.document.createElement('iframe');
    frame.title = 'Terms print frame';
    frame.style.position = 'fixed';
    frame.style.right = '0';
    frame.style.bottom = '0';
    frame.style.width = '0';
    frame.style.height = '0';
    frame.style.border = '0';
    window.document.body.appendChild(frame);

    const frameDocument = frame.contentDocument;
    const frameWindow = frame.contentWindow;
    if (!frameDocument || !frameWindow) {
      frame.remove();
      toast.error('Print preview is not ready yet.');
      return;
    }

    frameDocument.open();
    frameDocument.write(`<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title></title>
  ${styleContainer.innerHTML}
  <style>
    body { margin: 0; background: #fff; }
    .wmt-docx-preview-wrapper { padding: 0 !important; background: #fff !important; }
    @page { margin: 12mm; }
    @media print {
      html, body { margin: 0 !important; padding: 0 !important; }
      .wmt-docx-preview-wrapper { margin: 0 !important; padding: 0 !important; }
    }
  </style>
</head>
<body>${container.innerHTML}</body>
</html>`);
    frameDocument.close();

    frameWindow.focus();
    const previousTitle = window.document.title;
    window.document.title = '';
    window.setTimeout(() => {
      frameWindow.print();
      window.setTimeout(() => {
        window.document.title = previousTitle;
        frame.remove();
      }, 1000);
    }, 150);
  };

  const handleGenerate = async () => {
    const target = wk.trim();
    if (!target) {
      setStatus('Enter a workstation first.');
      toast.error('Enter a workstation first.');
      return;
    }

    setGenerating(true);
    setGeneratedDocument((current) => {
      if (current) {
        URL.revokeObjectURL(current.url);
      }
      return null;
    });
    setStatus('Loading WK data and generating DOCX...');
    try {
      const token = getStoredToken();
      const response = await fetch(`${API_BASE_URL}/api/terms/generate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          wk: target,
          employee_name: employeeName.trim(),
          term_type: termType,
        }),
      });

      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || 'Failed to generate DOCX.');
      }

      const blob = await response.blob();
      const filename = fileNameFromDisposition(
        response.headers.get('Content-Disposition'),
        `${target}-${termType}.docx`
      );
      const url = URL.createObjectURL(blob);
      const document = { url, filename, blob };
      setGeneratedDocument(document);

      const missing = response.headers.get('X-Missing-Placeholders');
      setStatus(missing ? `DOCX ready. Unused placeholders: ${missing}` : 'DOCX ready. Use Download to save it or Print to print.');
      toast.success('DOCX generated and ready');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to generate DOCX.';
      setStatus(message);
      toast.error(message);
    } finally {
      setGenerating(false);
    }
  };

  if (authLoading) {
    return null;
  }

  if (!user) {
    navigate('/login');
    return null;
  }

  return (
    <div className="flex h-screen bg-background">
      <Sidebar user={user.username} permissions={user.permissions} onLogout={handleLogout} />

      <main className="flex-1 overflow-auto">
        <div className="mx-auto flex max-w-6xl flex-col gap-8 p-6 lg:p-8">
          <header className="border-b border-border pb-6">
            <h1 className="text-3xl font-bold text-foreground">Terms</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Generate responsibility and return documents from workstation inventory data.
            </p>
          </header>

          <section className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_360px]">
            <div className="rounded-lg border border-border bg-card p-5">
              <div className="mb-5 flex items-center gap-2">
                <FileText size={18} className="text-primary" />
                <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  Responsibility and return terms
                </h2>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <label className="space-y-2">
                  <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">WK</span>
                  <div className="relative">
                    <Laptop className="absolute left-3 top-2.5 text-muted-foreground" size={18} />
                    <Input
                      value={wk}
                      onChange={(event) => setWk(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                          handleGenerate();
                        }
                      }}
                      placeholder="WKS048-1BR"
                      className="pl-10"
                    />
                  </div>
                </label>

                <label className="space-y-2">
                  <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Name</span>
                  <div className="relative">
                    <UserRound className="absolute left-3 top-2.5 text-muted-foreground" size={18} />
                    <Input
                      value={employeeName}
                      onChange={(event) => setEmployeeName(event.target.value)}
                      placeholder="Employee full name"
                      className="pl-10"
                    />
                  </div>
                </label>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-[minmax(0,1fr)_180px]">
                <label className="space-y-2">
                  <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Type</span>
                  <Select value={termType} onValueChange={(value) => setTermType(value as 'responsibility' | 'return')}>
                    <SelectTrigger className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {(config?.types || [
                        { value: 'responsibility', label: 'Responsibility and acceptance' },
                        { value: 'return', label: 'Equipment return' },
                      ]).map((type) => (
                        <SelectItem key={type.value} value={type.value}>
                          {type.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </label>

                <Button className="mt-auto gap-2" onClick={handleGenerate} disabled={generating}>
                  {generating ? <Loader2 className="animate-spin" size={16} /> : <FileText size={16} />}
                  Generate DOCX
                </Button>
              </div>

              <div className="mt-4 rounded-md border border-border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
                <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                  <p className="min-w-0 break-words">{status}</p>
                  {generatedDocument && (
                    <div className="flex shrink-0 flex-wrap gap-2">
                      <Button size="sm" variant="outline" className="gap-2" onClick={handleDownloadAgain}>
                        <Download size={14} />
                        Download
                      </Button>
                      <Button size="sm" variant="outline" className="gap-2" onClick={handleOpenForPrint} disabled={printing}>
                        {printing ? <Loader2 className="animate-spin" size={14} /> : <Printer size={14} />}
                        Print
                      </Button>
                    </div>
                  )}
                </div>
              </div>
            </div>

            <aside className="rounded-lg border border-border bg-card p-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-foreground">Document generation</h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    WMT reads the WK data and prepares the DOCX. Use Download when you want to save it.
                  </p>
                </div>
                <span className="rounded-md bg-primary/10 px-2 py-1 text-xs font-semibold text-primary">
                  DOCX
                </span>
              </div>

              <div className="mt-6 space-y-3">
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Filled fields</p>
                <div className="flex flex-wrap gap-2">
                  {(config?.placeholders || ['WKS', 'Serial Number', 'Model', 'Brand', 'Employee Name']).map((item) => (
                    <span key={item} className="rounded-md border border-border bg-muted/40 px-2 py-1 text-xs text-foreground">
                      {item}
                    </span>
                  ))}
                </div>
              </div>

              <div className="mt-6 rounded-md border border-border bg-muted/30 p-3 text-sm">
                <div className="flex items-center gap-2 text-foreground">
                  <CheckCircle2 size={16} className="text-primary" />
                  <span className="font-medium">Selected template</span>
                </div>
                <p className="mt-2 break-words text-xs text-muted-foreground">
                  {selectedType?.template_path || 'Loading template path...'}
                </p>
                {selectedType && !selectedType.template_accessible && (
                  <p className="mt-2 text-xs text-destructive">
                    Template is not accessible from this machine.
                  </p>
                )}
              </div>
            </aside>
          </section>
        </div>
      </main>

      {printPreview && (
        <div className="fixed inset-0 z-50 flex flex-col bg-background/95 backdrop-blur-sm">
          <div className="flex items-center justify-between gap-3 border-b border-border bg-card px-5 py-3">
            <div className="min-w-0">
              <p className="font-semibold text-foreground">Print Preview</p>
              <p className="truncate text-sm text-muted-foreground">{printPreview.filename}</p>
            </div>
            <div className="flex shrink-0 gap-2">
              <Button variant="outline" className="gap-2" onClick={() => downloadDocument(printPreview)}>
                <Download size={16} />
                Download original DOCX
              </Button>
              <Button className="gap-2" onClick={handlePrintPreview} disabled={previewRendering}>
                <Printer size={16} />
                Print
              </Button>
              <Button variant="outline" onClick={handleClosePreview}>
                Close
              </Button>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-auto bg-muted/40 p-4">
            <div ref={previewStyleRef} />
            <div className="mx-auto min-h-full max-w-[960px] rounded-md border border-border bg-background p-4 shadow-sm">
              {previewRendering && (
                <div className="flex h-40 items-center justify-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="animate-spin" size={16} />
                  Rendering DOCX preview...
                </div>
              )}
              <div
                ref={previewContainerRef}
                className={previewRendering ? 'hidden' : 'cursor-text rounded-sm outline-none focus-within:ring-2 focus-within:ring-primary/30'}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
