export const EXPERIMENT_DEVICES = [
  {
    key: 'oppo_1',
    label: '1号机 - OPPO',
    deviceToken: '120c83f761744a1e7e0',
  },
  {
    key: 'samsung_f52_2',
    label: '2号机 - 三星F52',
    deviceToken: '13065ffa4f24d1d8650',
  },
  {
    key: 'samsung_a53_3',
    label: '3号机 - 三星A53',
    deviceToken: '1a0018970bf6ef5906f',
  },
] as const

export const DEFAULT_EXPERIMENT_DEVICE_TOKEN = EXPERIMENT_DEVICES[0].deviceToken

export function isKnownExperimentDeviceToken(deviceToken: string): boolean {
  return EXPERIMENT_DEVICES.some((device) => device.deviceToken === deviceToken)
}
