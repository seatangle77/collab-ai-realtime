import { Capacitor, registerPlugin } from '@capacitor/core'

interface JPushDevicePlugin {
  getRegistrationId(): Promise<{ deviceToken: string }>
}

const JPushDevice = registerPlugin<JPushDevicePlugin>('JPushDevice')

export async function getJPushDeviceToken(): Promise<string> {
  if (!Capacitor.isNativePlatform()) {
    throw new Error('仅 Android App 内可读取 device_token')
  }

  const result = await JPushDevice.getRegistrationId()
  return result.deviceToken.trim()
}
