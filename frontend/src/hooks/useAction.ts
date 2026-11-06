import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'

export function useAction() {
  const client = useQueryClient()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  async function run<T>(action: () => Promise<T>, onSuccess?: (result: T) => void) {
    setPending(true)
    setError('')
    try {
      const result = await action()
      await client.invalidateQueries()
      onSuccess?.(result)
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Something went wrong. Please try again.')
    } finally { setPending(false) }
  }
  return { pending, error, run }
}
