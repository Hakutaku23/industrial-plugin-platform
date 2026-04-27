import { apiFetch } from './client'

export interface TemplateItem {
  name: string
  filename: string
  category: string
  title: string
  description: string
  download_url: string
}

export async function listTemplates(): Promise<TemplateItem[]> {
  const payload = await apiFetch<{ items: TemplateItem[] }>('/api/v1/templates')
  return payload.items
}
