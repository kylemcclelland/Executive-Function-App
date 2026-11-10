import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import './index.css'
import { DevotionView } from './components/devotions/DevotionView'
import data from '../../backend/scripts/seed_data/rosary_document.json'
import type { Devotion, PrayerText } from './types/devotions'

const source = { title: data.provenance, edition: null, translator: null, is_translation: false, attribution: 'Harness fixture: rights unverified', url: null, license_status: 'unverified' as const }
const texts: PrayerText[] = data.prayers.flatMap(p => [
  { id: `${p.key}-en`, slot: `collection-${p.key}`, language: 'en', title: p.heading_in_file.replace(/^The /, ''), body: p.english, source },
  { id: `${p.key}-la`, slot: `collection-${p.key}`, language: 'la', title: p.latin_title, body: p.latin, source },
])
const devotion: Devotion = { id: 'x', slug: 'the-holy-rosary', title: 'The Holy Rosary', subtitle: 'A prayer on the mysteries of the life of Jesus and Mary', category: 'Our Lady', estimated_minutes: 20, bookmarked: false, has_text: true, overview: 'Harness overview filler.', background: null, significance: null, references: [], instructions: [], steps: [], texts }
createRoot(document.getElementById('root')!).render(<MemoryRouter><DevotionView devotion={devotion} banner={<p style={{ margin: 8 }}>HARNESS FIXTURE: not real publication</p>} /></MemoryRouter>)
