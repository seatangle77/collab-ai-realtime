/**
 * useAudioRecorder
 *
 * 统一录音接口，根据运行环境自动选择：
 * - App（Android）→ capacitor-voice-recorder（原生录音，每 3s 分块）
 * - 浏览器        → MediaRecorder（WebM，每 1s 分块）
 */
import { ref } from 'vue'
import { Capacitor } from '@capacitor/core'

export type ChunkCallback = (blob: Blob, mimeType: string) => void

export function useAudioRecorder() {
  const isRecording = ref(false)

  // ── 浏览器模式 ───────────────────────────────────────────────
  let mediaRecorder: MediaRecorder | null = null
  let mediaStream: MediaStream | null = null

  // ── App 模式 ─────────────────────────────────────────────────
  let nativeChunkTimer: ReturnType<typeof setInterval> | null = null
  const NATIVE_CHUNK_INTERVAL_MS = 3000

  // ── 回调注册 ─────────────────────────────────────────────────
  let chunkCallback: ChunkCallback | null = null

  function onChunk(cb: ChunkCallback) {
    chunkCallback = cb
  }

  // ── 工具函数 ─────────────────────────────────────────────────

  /** base64 字符串 → Blob */
  function base64ToBlob(base64: string, mimeType: string): Blob {
    const binary = atob(base64)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i)
    }
    return new Blob([bytes], { type: mimeType })
  }

  // ── 浏览器模式实现 ────────────────────────────────────────────

  async function startBrowser(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('当前浏览器不支持录音')
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
    mediaStream = stream
    mediaRecorder = recorder

    recorder.ondataavailable = (event) => {
      if (!event.data || event.data.size === 0) return
      chunkCallback?.(event.data, event.data.type || 'audio/webm')
    }
    recorder.start(1000)
  }

  function stopBrowser(): void {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop()
    }
    mediaRecorder = null
    if (mediaStream) {
      mediaStream.getTracks().forEach((t) => t.stop())
      mediaStream = null
    }
  }

  // ── App 模式实现 ──────────────────────────────────────────────

  async function startNative(): Promise<void> {
    const { VoiceRecorder } = await import('capacitor-voice-recorder')
    const { KeepAwake } = await import('@capacitor-community/keep-awake')

    // 申请麦克风权限
    const permResult = await VoiceRecorder.hasAudioRecordingPermission()
    if (!permResult.value) {
      const req = await VoiceRecorder.requestAudioRecordingPermission()
      if (!req.value) {
        throw new Error('麦克风权限被拒绝，请在设置中开启')
      }
    }

    // 防息屏
    await KeepAwake.keepAwake()

    // 开始录音
    await VoiceRecorder.startRecording()

    // 定时分块：每 3s 停录 → 取数据 → 触发回调 → 继续录
    nativeChunkTimer = setInterval(async () => {
      try {
        const result = await VoiceRecorder.stopRecording()
        const { recordDataBase64, mimeType } = result.value
        if (recordDataBase64) {
          const blob = base64ToBlob(recordDataBase64, mimeType || 'audio/aac')
          chunkCallback?.(blob, mimeType || 'audio/aac')
        }
        // 继续录下一块
        await VoiceRecorder.startRecording()
      } catch {
        // 若本轮出错，忽略，继续下一轮
      }
    }, NATIVE_CHUNK_INTERVAL_MS)
  }

  async function stopNative(): Promise<void> {
    const { VoiceRecorder } = await import('capacitor-voice-recorder')
    const { KeepAwake } = await import('@capacitor-community/keep-awake')

    // 清除定时器
    if (nativeChunkTimer) {
      clearInterval(nativeChunkTimer)
      nativeChunkTimer = null
    }

    // 取最后一块数据
    try {
      const result = await VoiceRecorder.stopRecording()
      const { recordDataBase64, mimeType } = result.value
      if (recordDataBase64) {
        const blob = base64ToBlob(recordDataBase64, mimeType || 'audio/aac')
        chunkCallback?.(blob, mimeType || 'audio/aac')
      }
    } catch {
      // 若录音已结束则忽略
    }

    // 释放屏幕常亮
    await KeepAwake.allowSleep()
  }

  // ── 统一对外接口 ──────────────────────────────────────────────

  async function startRecording(): Promise<void> {
    if (isRecording.value) return
    if (Capacitor.isNativePlatform()) {
      await startNative()
    } else {
      await startBrowser()
    }
    isRecording.value = true
  }

  async function stopRecording(): Promise<void> {
    if (!isRecording.value) return
    if (Capacitor.isNativePlatform()) {
      await stopNative()
    } else {
      stopBrowser()
    }
    isRecording.value = false
  }

  return {
    isRecording,
    onChunk,
    startRecording,
    stopRecording,
  }
}
