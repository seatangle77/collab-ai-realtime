/**
 * 解析后端错误响应。后端通常返回 {"detail": "..."} 或 {"message": "..."}，
 * appHttp 会将响应体原始文本作为 Error.message 抛出。
 * 此函数尝试解析 JSON，提取可读错误文本，失败则原样返回。
 */
export function extractErrorMessage(e: unknown): string {
  const msg = (e as Error)?.message ?? String(e)
  try {
    const obj = JSON.parse(msg)
    return obj.detail ?? obj.message ?? msg
  } catch {
    return msg
  }
}
