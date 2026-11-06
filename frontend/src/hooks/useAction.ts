import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

export function useAction() {
  const client = useQueryClient()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  async function run(action: () => Promise<unknown>, onSuccess?: () => void) {
    setPending(true)
    setError('')
    try {
      await action()
      await client.invalidateQueries()
      onSuccess?.()
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Something went wrong. Please try again.')
    } finally { setPending(false) }
  }
  return { pending, error, run }
}
