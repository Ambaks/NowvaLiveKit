import { useState, useCallback, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Mic, Phone, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { authFetch } from '@/api/client';
import { trackEvent } from '@/lib/analytics';
import {
  LiveKitRoom,
  useVoiceAssistant,
  RoomAudioRenderer,
  VoiceAssistantControlBar,
  useRoomContext,
} from '@livekit/components-react';
import '@livekit/components-styles';

interface VoiceInterfaceProps {
  onComplete?: () => void;
}

type ConnectionState = 'initial' | 'requesting-token' | 'connecting' | 'connected' | 'completing' | 'disconnected' | 'error';

export const VoiceInterface = ({ onComplete }: VoiceInterfaceProps) => {
  const [connectionState, setConnectionState] = useState<ConnectionState>('initial');
  const [token, setToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [roomName, setRoomName] = useState<string | null>(null);
  const [programGenerated, setProgramGenerated] = useState<boolean>(false);

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
  const livekitUrl = import.meta.env.VITE_LIVEKIT_URL || '';

  // Get email from localStorage (set by EmailGate)
  const email = localStorage.getItem('nowva_user_email');

  const requestToken = useCallback(async () => {
    if (!email) {
      setError('No email found. Please refresh and try again.');
      setConnectionState('error');
      return;
    }

    setConnectionState('requesting-token');
    setError(null);
    trackEvent('voice_session_start');

    try {
      const response = await authFetch(`${apiUrl}/api/livekit/token`, {
        method: 'POST',
        body: JSON.stringify({}),
      });

      if (!response.ok) {
        throw new Error(`Failed to get room token: ${response.statusText}`);
      }

      const data = await response.json();
      setToken(data.token);
      setRoomName(data.room_name);
      setConnectionState('connecting');
    } catch (err) {
      console.error('Failed to request token:', err);
      setError(err instanceof Error ? err.message : 'Failed to connect to voice agent');
      setConnectionState('error');
    }
  }, [email, apiUrl]);

  const handleDisconnect = useCallback(() => {
    // Only transition to disconnected if not already completing
    // This handles early disconnects by the user
    if (connectionState !== 'completing') {
      setConnectionState('disconnected');
      setToken(null);
      setRoomName(null);
    }
  }, [connectionState]);

  const handleConnected = useCallback(() => {
    setConnectionState('connected');
  }, []);

  const handleError = useCallback((error: Error) => {
    console.error('Room connection error:', error);
    setError(error.message);
    setConnectionState('error');
  }, []);

  if (!email) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="max-w-2xl mx-auto"
      >
        <Card className="p-8 text-center">
          <AlertCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <h3 className="text-heading-lg font-semibold mb-2">Email Required</h3>
          <p className="text-foreground-secondary">
            Please enter your email address first to use the voice interface.
          </p>
        </Card>
      </motion.div>
    );
  }

  const handleProgramGenerating = useCallback(() => {
    trackEvent('program_generated', { path: 'voice' });
    setProgramGenerated(true);
    setConnectionState('completing');
    // Disconnect after 5 seconds
    setTimeout(() => {
      setConnectionState('disconnected');
      setToken(null);
      setRoomName(null);
      if (onComplete) {
        onComplete();
      }
    }, 5000);
  }, [onComplete]);

  // Show the LiveKit room when we have a token
  if (token && roomName && connectionState !== 'disconnected') {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="max-w-3xl mx-auto"
      >
        <LiveKitRoom
          token={token}
          serverUrl={livekitUrl}
          connect={true}
          audio={true}
          video={false}
          options={{
            publishDefaults: {
              preConnectBuffer: true,
            },
          }}
          onConnected={handleConnected}
          onDisconnected={handleDisconnect}
          onError={handleError}
          className="livekit-room"
        >
          <VoiceAssistantUI
            connectionState={connectionState}
            onProgramGenerating={handleProgramGenerating}
          />
        </LiveKitRoom>
      </motion.div>
    );
  }

  // Initial state - show "Talk to Nova" button
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="max-w-2xl mx-auto"
    >
      <Card className="p-12 text-center">
        <AnimatePresence mode="wait">
          {connectionState === 'initial' && (
            <motion.div
              key="initial"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <div className="w-24 h-24 mx-auto mb-6 bg-accent/10 rounded-full flex items-center justify-center">
                <Mic className="w-12 h-12 text-accent" />
              </div>
              <h3 className="text-heading-lg font-semibold mb-4">Ready to Talk to Nova?</h3>
              <p className="text-foreground-secondary mb-8">
                Have a natural conversation with Nova to create your personalized workout program.
                The conversation takes about 3-5 minutes.
              </p>
              <button
                onClick={requestToken}
                className="bg-accent hover:bg-accent/90 text-white px-8 py-4 rounded-lg font-semibold text-lg transition-colors inline-flex items-center gap-3"
              >
                <Phone className="w-6 h-6" />
                Talk to Nova
              </button>
            </motion.div>
          )}

          {connectionState === 'requesting-token' && (
            <motion.div
              key="requesting"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <Loader2 className="w-16 h-16 text-accent mx-auto mb-4 animate-spin" />
              <h3 className="text-heading-lg font-semibold mb-2">Setting Up Connection...</h3>
              <p className="text-foreground-secondary">This will just take a moment</p>
            </motion.div>
          )}

          {connectionState === 'connecting' && (
            <motion.div
              key="connecting"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <Loader2 className="w-16 h-16 text-accent mx-auto mb-4 animate-spin" />
              <h3 className="text-heading-lg font-semibold mb-2">Connecting to Nova...</h3>
              <p className="text-foreground-secondary">Getting ready to chat</p>
            </motion.div>
          )}

          {connectionState === 'disconnected' && programGenerated && (
            <motion.div
              key="disconnected-success"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <CheckCircle2 className="w-16 h-16 text-green-500 mx-auto mb-4" />
              <h3 className="text-heading-lg font-semibold mb-2">Conversation Complete</h3>
              <p className="text-foreground-secondary">
                Your program has been submitted for generation.
                You'll receive it via email within 5 minutes! If you don't see it, check your spam folder.
              </p>
              <p className="text-foreground-tertiary text-sm mt-4">
                You can generate a new program once every 20 minutes.
              </p>
            </motion.div>
          )}

          {connectionState === 'disconnected' && !programGenerated && (
            <motion.div
              key="disconnected-early"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <AlertCircle className="w-16 h-16 text-yellow-500 mx-auto mb-4" />
              <h3 className="text-heading-lg font-semibold mb-2">Conversation Ended Early</h3>
              <p className="text-foreground-secondary mb-6">
                The conversation was disconnected before your program could be generated.
                No program was created.
              </p>
              <button
                onClick={() => {
                  setConnectionState('initial');
                  setProgramGenerated(false);
                  setError(null);
                }}
                className="bg-accent hover:bg-accent/90 text-white px-6 py-3 rounded-lg font-semibold transition-colors"
              >
                Try Again
              </button>
            </motion.div>
          )}

          {connectionState === 'error' && (
            <motion.div
              key="error"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <AlertCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />
              <h3 className="text-heading-lg font-semibold mb-2">Connection Error</h3>
              <p className="text-foreground-secondary mb-6">
                {error || 'Failed to connect to the voice agent. Please try again.'}
              </p>
              <button
                onClick={() => {
                  setConnectionState('initial');
                  setError(null);
                }}
                className="bg-accent hover:bg-accent/90 text-white px-6 py-3 rounded-lg font-semibold transition-colors"
              >
                Try Again
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>
    </motion.div>
  );
};

// Custom animated sound bars component
function AnimatedSoundBars({ isActive }: { isActive: boolean }) {
  const bars = 40;

  return (
    <div className="flex items-center justify-center gap-1 h-full py-8">
      {Array.from({ length: bars }).map((_, i) => {
        const delay = i * 0.05;
        const duration = 0.6 + Math.random() * 0.4;

        return (
          <motion.div
            key={i}
            className="w-1 rounded-full bg-gradient-to-t from-accent-dark via-accent to-accent-light"
            animate={isActive ? {
              height: [
                `${20 + Math.random() * 20}%`,
                `${60 + Math.random() * 40}%`,
                `${20 + Math.random() * 20}%`,
              ],
              opacity: [0.5, 1, 0.5],
            } : {
              height: '20%',
              opacity: 0.3,
            }}
            transition={{
              duration,
              repeat: Infinity,
              delay,
              ease: "easeInOut",
            }}
          />
        );
      })}
    </div>
  );
}

// Inner component that has access to LiveKit hooks
function VoiceAssistantUI({
  connectionState,
  onProgramGenerating
}: {
  connectionState: ConnectionState;
  onProgramGenerating: () => void;
}) {
  const { state, audioTrack } = useVoiceAssistant();
  const room = useRoomContext();
  const isActive = state === 'speaking' || state === 'thinking';

  // Listen for data messages from the agent
  useEffect(() => {
    if (!room) return;

    const handleDataReceived = (payload: Uint8Array) => {
      try {
        const decoder = new TextDecoder();
        const text = decoder.decode(payload);
        const data = JSON.parse(text);

        console.log('[VoiceInterface] Received data message:', data);

        if (data.type === 'program_generating') {
          console.log('[VoiceInterface] Program generation started, triggering completion screen');
          onProgramGenerating();
        }
      } catch (error) {
        console.error('[VoiceInterface] Error parsing data message:', error);
      }
    };

    room.on('dataReceived', handleDataReceived);

    return () => {
      room.off('dataReceived', handleDataReceived);
    };
  }, [room, onProgramGenerating]);

  // Show completion state when completing
  if (connectionState === 'completing') {
    return (
      <Card className="p-12 text-center">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0 }}
        >
          <CheckCircle2 className="w-16 h-16 text-green-500 mx-auto mb-4" />
          <h3 className="text-heading-lg font-semibold mb-2">Program Submitted!</h3>
          <p className="text-foreground-secondary">
            Your personalized workout program is being generated now.
            You'll receive it via email within the next 10 minutes!
          </p>
          <p className="text-foreground-tertiary text-sm mt-4">
            Be sure to check your spam folder if you don't see it.
          </p>
        </motion.div>
      </Card>
    );
  }

  return (
    <Card className="p-8">
      <div className="text-center mb-8">
        <div className="inline-flex items-center gap-3 mb-4">
          <h3 className="text-heading-lg font-semibold">Talking with Nova</h3>
          <Badge variant={connectionState === 'connected' ? 'success' : 'secondary'}>
            {connectionState === 'connected' ? 'Connected' : 'Connecting...'}
          </Badge>
        </div>
      </div>

      {/* Audio visualization with animated sound bars */}
      <div className="mb-8 h-40 bg-background-secondary rounded-lg flex items-center justify-center overflow-hidden">
        {audioTrack ? (
          <AnimatedSoundBars isActive={isActive} />
        ) : (
          <div className="flex items-center gap-2 text-foreground-secondary">
            <Loader2 className="w-5 h-5 animate-spin" />
            <span>Waiting for audio...</span>
          </div>
        )}
      </div>

      {/* Agent state indicator */}
      <div className="mb-6 text-center">
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-background-secondary rounded-full">
          {state === 'listening' && (
            <>
              <Mic className="w-4 h-4 text-green-500" />
              <span className="text-sm font-medium">Listening...</span>
            </>
          )}
          {state === 'thinking' && (
            <>
              <Loader2 className="w-4 h-4 text-accent animate-spin" />
              <span className="text-sm font-medium">Thinking...</span>
            </>
          )}
          {state === 'speaking' && (
            <>
              <div className="w-4 h-4 bg-accent rounded-full animate-pulse" />
              <span className="text-sm font-medium">Speaking...</span>
            </>
          )}
          {state === 'idle' && (
            <>
              <div className="w-4 h-4 bg-foreground-secondary/30 rounded-full" />
              <span className="text-sm font-medium text-foreground-secondary">Idle</span>
            </>
          )}
        </div>
      </div>

      {/* Control bar */}
      <VoiceAssistantControlBar />

      {/* Hidden audio renderer (required for audio playback) */}
      <RoomAudioRenderer />

      {/* Instructions */}
      <div className="mt-8 p-4 bg-background-secondary rounded-lg">
        <p className="text-sm text-foreground-secondary text-center">
          Speak naturally with Nova. She'll guide you through creating your personalized program.
          The conversation takes about 3-5 minutes.
        </p>
      </div>
    </Card>
  );
}
