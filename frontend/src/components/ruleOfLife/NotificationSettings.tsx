import { useState } from 'react'
import { Bell, BellOff } from 'lucide-react'
import { Card } from '../ui'
import { Button } from '../ui'
import { useAction } from '../../hooks/useAction'
import { ErrorMessage } from '../common'
import {
  disablePushNotifications, enablePushNotifications, permissionState, pushSupported,
  useBrowserSubscription, usePushConfig, usePushStatus, useRefreshPushState,
} from '../../lib/pushNotifications'

/** Notification settings for this browser. "Reminders enabled" is claimed only when the server
 * itself reports scheduled delivery active; a bare subscription shows as ready-but-pending.
 * Permission is requested exclusively from the Enable button, and a past denial is explained,
 * not re-prompted. */
export function NotificationSettings() {
  const config = usePushConfig()
  const status = usePushStatus()
  const subscription = useBrowserSubscription()
  const refresh = useRefreshPushState()
  const action = useAction()
  const [permission, setPermission] = useState(permissionState())

  const body = () => {
    if (!pushSupported()) return <p className="muted">Your browser does not support push notifications.</p>
    if (config.isPending || subscription.isPending) return <p className="muted">Checking notification settings…</p>
    if (config.isError || !config.data?.configured || !config.data.public_key)
      return <p className="muted">Push notifications are not available on this server yet.</p>
    const publicKey = config.data.public_key
    if (permission === 'denied')
      return <p className="muted"><BellOff size={13} aria-hidden="true" /> Notifications are blocked in your browser settings. To receive prayer reminders, allow notifications for this site in your browser, then return here.</p>
    if (permission === 'granted' && subscription.data)
      return <>
        <p className="muted"><Bell size={13} aria-hidden="true" /> {status.data?.delivery === 'active'
          ? 'Prayer reminders are enabled for this browser. Each prayer with its reminder turned on will be announced at its time.'
          : 'This browser is ready for notifications. Scheduled reminders are not active yet.'}</p>
        <Button variant="outline" size="sm" disabled={action.pending}
          onClick={() => void action.run(async () => { await disablePushNotifications(); refresh() })}>
          Disable notifications in this browser
        </Button>
      </>
    return <>
      <p className="muted">Enable notifications to receive prayer reminders. Your browser will ask for permission; nothing is requested until you choose to.</p>
      <Button size="sm" disabled={action.pending}
        onClick={() => void action.run(async () => { setPermission(await enablePushNotifications(publicKey)); refresh() })}>
        <Bell size={14} aria-hidden="true" /> Enable notifications
      </Button>
    </>
  }

  return <Card className="rule-card">
    <h2 className="rule-settings-title">Notifications</h2>
    {body()}
    <ErrorMessage message={action.error} />
  </Card>
}
