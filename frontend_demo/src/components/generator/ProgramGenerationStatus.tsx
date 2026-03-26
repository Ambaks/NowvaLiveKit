import { useEffect, useRef, useState, useCallback } from 'react';
import { motion } from 'framer-motion';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Loader2, CheckCircle2, XCircle, Download } from 'lucide-react';
import { programsApi } from '@/api/programs';
import type { JobStatusResponse } from '@/api/programs';

interface ProgramGenerationStatusProps {
  jobId: string;
  onComplete: (programId: string) => void;
  onError: (error: string) => void;
  onReset: () => void;
}

export const ProgramGenerationStatus = ({
  jobId,
  onComplete,
  onError,
  onReset,
}: ProgramGenerationStatusProps) => {
  const [status, setStatus] = useState<JobStatusResponse | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);
  const doneRef = useRef(false);
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);

  // Keep refs up to date without re-triggering the effect
  onCompleteRef.current = onComplete;
  onErrorRef.current = onError;

  useEffect(() => {
    doneRef.current = false;
    let intervalId: number;

    const checkStatus = async () => {
      if (doneRef.current) return;

      try {
        const statusData = await programsApi.getJobStatus(jobId);
        setStatus(statusData);

        if (statusData.status === 'completed' && statusData.program_id) {
          doneRef.current = true;
          clearInterval(intervalId);
          onCompleteRef.current(statusData.program_id);
        } else if (statusData.status === 'failed') {
          doneRef.current = true;
          clearInterval(intervalId);
          onErrorRef.current(statusData.error_message || 'Program generation failed');
        }
      } catch (error) {
        console.error('Error checking status:', error);
        doneRef.current = true;
        clearInterval(intervalId);
        onErrorRef.current('Failed to check generation status');
      }
    };

    // Check immediately
    checkStatus();

    // Poll every 2 seconds
    intervalId = window.setInterval(checkStatus, 2000);

    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [jobId]);

  const handleDownload = async () => {
    if (!status?.program_id) return;

    setIsDownloading(true);
    try {
      const blob = await programsApi.getProgramPdf(status.program_id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `workout-program-${status.program_id}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Error downloading PDF:', error);
      alert('Failed to download PDF');
    } finally {
      setIsDownloading(false);
    }
  };

  const getStatusIcon = () => {
    if (!status) return <Loader2 className="w-16 h-16 text-accent animate-spin" />;

    switch (status.status) {
      case 'completed':
        return <CheckCircle2 className="w-16 h-16 text-green-500" />;
      case 'failed':
        return <XCircle className="w-16 h-16 text-red-500" />;
      default:
        return <Loader2 className="w-16 h-16 text-accent animate-spin" />;
    }
  };

  const getStatusMessage = () => {
    if (!status) return 'Initializing...';

    switch (status.status) {
      case 'pending':
        return 'Preparing your program...';
      case 'processing':
        return `Generating your program... (Week ${status.current_week || 0} of ${status.total_weeks || 0})`;
      case 'completed':
        return 'Your program is ready!';
      case 'failed':
        return status.error_message || 'Generation failed';
      default:
        return 'Processing...';
    }
  };

  const progress = status?.progress || 0;

  return (
    <div className="max-w-2xl mx-auto">
      <Card className="p-12 text-center">
        <motion.div
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          className="mb-6 flex justify-center"
        >
          {getStatusIcon()}
        </motion.div>

        <h3 className="text-heading-lg font-semibold mb-2">
          {getStatusMessage()}
        </h3>

        <div className="mt-6 mb-8">
          <div className="w-full bg-surface-light rounded-full h-3 overflow-hidden">
            <motion.div
              className="h-full bg-gradient-to-r from-accent to-accent-light"
              initial={{ width: 0 }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.5 }}
            />
          </div>
          <p className="text-sm text-foreground-tertiary mt-2">{progress}% complete</p>
        </div>

        {status?.status === 'completed' && status.program_id && (
          <div className="space-y-3">
            <Button
              onClick={handleDownload}
              disabled={isDownloading}
              className="w-full flex items-center justify-center gap-2"
            >
              {isDownloading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Downloading...
                </>
              ) : (
                <>
                  <Download className="w-4 h-4" />
                  Download PDF
                </>
              )}
            </Button>
            <Button
              onClick={onReset}
              variant="secondary"
              className="w-full"
            >
              Generate Another Program
            </Button>
          </div>
        )}

        {status?.status === 'failed' && (
          <Button onClick={onReset} variant="secondary" className="w-full">
            Try Again
          </Button>
        )}

        {status?.status === 'processing' && (
          <p className="text-sm text-foreground-secondary mt-4">
            This typically takes 30-60 seconds. Please don't close this page.
          </p>
        )}
      </Card>
    </div>
  );
};
