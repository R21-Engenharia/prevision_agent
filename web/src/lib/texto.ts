/**
 * Normalização de texto para busca: minúsculas e sem acentos.
 *
 * Precisa espelhar `_norm()` da API (api/main.py). Se as duas divergirem, o
 * relatório exportado não bate com o que está na tela — foi o que acontecia
 * quando o cliente usava só toLowerCase(): buscar "instalacao" sem acento
 * mostrava 0 na tela mas exportava 16 linhas.
 */
export function normalizar(texto: string): string {
  return texto.normalize('NFKD').replace(/\p{Diacritic}/gu, '').toLowerCase()
}
