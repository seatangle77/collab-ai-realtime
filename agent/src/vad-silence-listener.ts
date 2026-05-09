import { getRedisSubscriber } from './cache/redis-client';
import { createLogger } from './logger';

const logger = createLogger('vad-silence-listener');
export const VAD_SILENCE_CHANNEL = 'agent:vad_silence';

export interface VadSilenceEvent {
  session_id: string;
  silence_ms?: number;
  last_voice_at_ms?: number;
}

export type VadSilenceHandler = (event: VadSilenceEvent) => void | Promise<void>;

export class VadSilenceListener {
  private started = false;

  constructor(private readonly handler: VadSilenceHandler) {}

  async start(): Promise<void> {
    if (this.started) return;

    const subscriber = await getRedisSubscriber();
    if (!subscriber) {
      logger.info('Redis unavailable; VAD silence pub/sub listener disabled');
      return;
    }

    await subscriber.subscribe(VAD_SILENCE_CHANNEL, (message) => {
      void this.handleMessage(message);
    });
    this.started = true;
    logger.info('VAD silence listener subscribed', { channel: VAD_SILENCE_CHANNEL });
  }

  async stop(): Promise<void> {
    if (!this.started) return;
    const subscriber = await getRedisSubscriber();
    if (!subscriber) return;

    await subscriber.unsubscribe(VAD_SILENCE_CHANNEL);
    this.started = false;
    logger.info('VAD silence listener unsubscribed', { channel: VAD_SILENCE_CHANNEL });
  }

  private async handleMessage(message: string): Promise<void> {
    let event: VadSilenceEvent;
    try {
      event = JSON.parse(message) as VadSilenceEvent;
    } catch (err) {
      logger.warn('invalid VAD silence event JSON', { message: (err as Error).message });
      return;
    }

    if (!event.session_id) {
      logger.warn('invalid VAD silence event payload: missing session_id');
      return;
    }

    await this.handler(event);
  }
}
