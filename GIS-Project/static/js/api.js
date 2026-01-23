export async function getJSON(url) {
  const res = await fetch(url, { headers: { "Accept": "application/json" } });
  if (!res.ok) throw new Error(`Request failed: ${res.status}`);
  return await res.json();
}
