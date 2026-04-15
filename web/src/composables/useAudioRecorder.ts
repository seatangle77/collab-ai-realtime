/**
 * useAudioRecorder
 *
 * 统一录音接口，根据运行环境自动选择：
 * - App（Android）→ capacitor-voice-recorder（原生录音，每 1s 分块）
 * - 浏览器        → MediaRecorder（WebM，每 0.5s 分块）
 */
import { ref } from 'vue'
import { Capacitor } from '@capacitor/core'

export type ChunkCallback = (blob: Blob, mimeType: string) => void

export function useAudioRecorder() {
  const isRecording = ref(false)
  const recordingSource = ref<'microphone' | 'file' | null>(null)

  // ── 浏览器模式 ───────────────────────────────────────────────
  let mediaRecorder: MediaRecorder | null = null
  let mediaStream: MediaStream | null = null
  let injectedAudioContext: AudioContext | null = null
  let injectedAudioElement: HTMLAudioElement | null = null
  let injectedObjectUrl: string | null = null
  let injectedSourceNode: MediaElementAudioSourceNode | null = null
  let injectedDestinationNode: MediaStreamAudioDestinationNode | null = null

  // ── App 模式 ─────────────────────────────────────────────────
  let nativeChunkTimer: ReturnType<typeof setInterval> | null = null
  const NATIVE_CHUNK_INTERVAL_MS = 1000
  const BROWSER_CHUNK_INTERVAL_MS = 500

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

  function getBrowserRecorderOptions(): MediaRecorderOptions | undefined {
    if (typeof MediaRecorder === 'undefined') return undefined
    if (MediaRecorder.isTypeSupported('audio/webm')) {
      return { mimeType: 'audio/webm' }
    }
    return undefined
  }

  function bindBrowserRecorder(stream: MediaStream): MediaRecorder {
    const recorder = new MediaRecorder(stream, getBrowserRecorderOptions())
    mediaStream = stream
    mediaRecorder = recorder

    recorder.ondataavailable = (event) => {
      if (!event.data || event.data.size === 0) return
      chunkCallback?.(event.data, event.data.type || 'audio/webm')
    }

    recorder.onstop = () => {
      cleanupInjectedAudio()
    }

    return recorder
  }

  async function startBrowser(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('当前浏览器不支持录音')
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const recorder = bindBrowserRecorder(stream)
    recorder.start(BROWSER_CHUNK_INTERVAL_MS)
  }

  function cleanupInjectedAudio(): void {
    if (injectedAudioElement) {
      injectedAudioElement.pause()
      injectedAudioElement.src = ''
      injectedAudioElement.onended = null
      injectedAudioElement.onerror = null
      injectedAudioElement = null
    }
    injectedSourceNode?.disconnect()
    injectedDestinationNode?.disconnect()
    injectedSourceNode = null
    injectedDestinationNode = null
    if (injectedObjectUrl) {
      URL.revokeObjectURL(injectedObjectUrl)
      injectedObjectUrl = null
    }
    if (injectedAudioContext) {
      void injectedAudioContext.close()
      injectedAudioContext = null
    }
  }

  async function startBrowserInjectedFile(file: File): Promise<void> {
    if (typeof window === 'undefined' || typeof AudioContext === 'undefined') {
      throw new Error('当前环境不支持文件注入录音')
    }

    cleanupInjectedAudio()

    const audioContext = new AudioContext()
    const destination = audioContext.createMediaStreamDestination()
    const audio = new Audio()
    const objectUrl = URL.createObjectURL(file)

    audio.src = objectUrl
    audio.preload = 'auto'
    audio.crossOrigin = 'anonymous'

    const sourceNode = audioContext.createMediaElementSource(audio)
    sourceNode.connect(destination)

    injectedAudioContext = audioContext
    injectedAudioElement = audio
    injectedObjectUrl = objectUrl
    injectedSourceNode = sourceNode
    injectedDestinationNode = destination

    const recorder = bindBrowserRecorder(destination.stream)
    audio.onended = () => {
      void stopRecording().catch(() => {
        // Ignore auto-stop cleanup failures.
      })
    }
    audio.onerror = () => {
      void stopRecording().catch(() => {
        // Ignore auto-stop cleanup failures.
      })
    }

    try {
      recorder.start(BROWSER_CHUNK_INTERVAL_MS)
      await audioContext.resume()
      await audio.play()
    } catch (error) {
      stopBrowser()
      throw error instanceof Error ? error : new Error('文件注入启动失败')
    }
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
    cleanupInjectedAudio()
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

    // 防御：如果 native 插件上一次录音未正常释放（如直接返回列表），先强制停掉
    try {
      await VoiceRecorder.stopRecording()
    } catch {
      // 没有在录音时 stop 会抛错，忽略即可
    }

    // 开始录音
    await VoiceRecorder.startRecording()

    // 定时分块：每 1s 停录 → 取数据 → 触发回调 → 继续录
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
    recordingSource.value = 'microphone'
  }

  async function startFileInjection(file: File): Promise<void> {
    if (isRecording.value) return
    if (Capacitor.isNativePlatform()) {
      throw new Error('原生端暂不支持文件注入模式')
    }
    await startBrowserInjectedFile(file)
    isRecording.value = true
    recordingSource.value = 'file'
  }

  async function stopRecording(): Promise<void> {
    if (!isRecording.value) return
    if (Capacitor.isNativePlatform()) {
      await stopNative()
    } else {
      stopBrowser()
    }
    isRecording.value = false
    recordingSource.value = null
  }

  return {
    isRecording,
    recordingSource,
    onChunk,
    startRecording,
    startFileInjection,
    stopRecording,
  }
}
