import ReactMarkdown from 'react-markdown'

/**
 * Renders user-authored Markdown safely: raw HTML is never rendered, unsafe URL schemes
 * (e.g. javascript:) are stripped by react-markdown, images are not loaded, and links open
 * without leaking the opener.
 */
export function Markdown({ children }: { children: string }) {
  return <div className="markdown"><ReactMarkdown
    disallowedElements={['img', 'script', 'iframe', 'object', 'embed']}
    unwrapDisallowed
    components={{ a: ({ href, children: label }) => href ? <a href={href} target="_blank" rel="noopener noreferrer">{label}</a> : <span>{label}</span> }}
  >{children}</ReactMarkdown></div>
}
