// Normalizes an Axios error's response body into a string that's always
// safe to render directly in JSX.
//
// FastAPI's `detail` is a plain string for a manually-raised HTTPException,
// but a LIST of {type, loc, msg, input, ctx} objects for an automatic
// Pydantic validation error (e.g. a blank required field). Rendering that
// list directly as a JSX child crashes with "Objects are not valid as a
// React child" — confirmed live via a blank Risk Email Template submit,
// which hits RiskEmailTemplateUpdate's `min_length=1` and 422s with the
// list form.
export function getErrorMessage(err, fallback = 'Something went wrong.') {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map(d => (typeof d === 'string' ? d : d?.msg))
      .filter(Boolean)
      .join(' ') || fallback;
  }
  return fallback;
}
