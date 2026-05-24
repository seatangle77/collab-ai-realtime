import { LocalNotifications } from '@capacitor/local-notifications'

const TEST_NOTIFICATION_BODY =
  '你说‘有时候搞抽象’难界定——难在是别人看不懂，还是你自己不确定想表达什么？'

export async function sendLocalTestNotification(): Promise<void> {
  const permission = await LocalNotifications.checkPermissions()
  if (permission.display !== 'granted') {
    const requested = await LocalNotifications.requestPermissions()
    if (requested.display !== 'granted') {
      throw new Error('通知权限未开启')
    }
  }

  await LocalNotifications.schedule({
    notifications: [
      {
        id: Date.now() % 2147483647,
        title: '',
        body: TEST_NOTIFICATION_BODY,
        schedule: { at: new Date(Date.now() + 500) },
      },
    ],
  })
}
