// Escapes text before it is put into an innerHTML template, so names, descriptions
// and other visitor-supplied text can never run as code (stops "stored XSS").
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}
