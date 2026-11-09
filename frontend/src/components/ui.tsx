import * as React from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { Button } from './ui/button'
export { Button } from './ui/button'
export { Input } from './ui/input'
export { Card } from './ui/card'

export function Dialog({ open, onOpenChange, title, description, children }: { open: boolean; onOpenChange: (open: boolean) => void; title: string; description?: string; children: React.ReactNode }) {
  const descriptionId = React.useId()
  return <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="dialog-overlay" />
      <DialogPrimitive.Content className="dialog-content" aria-describedby={description ? descriptionId : undefined} onEscapeKeyDown={event => { const target = event.target as HTMLElement | null; if (target?.getAttribute?.('role') === 'combobox' && target.getAttribute('aria-expanded') === 'true') event.preventDefault() }}>
        <div className="dialog-heading">
          <DialogPrimitive.Title>{title}</DialogPrimitive.Title>
          <DialogPrimitive.Close asChild><Button variant="ghost" size="icon" aria-label="Close dialog"><X size={20} /></Button></DialogPrimitive.Close>
        </div>
        {description && <DialogPrimitive.Description id={descriptionId} className="muted">{description}</DialogPrimitive.Description>}
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  </DialogPrimitive.Root>
}
