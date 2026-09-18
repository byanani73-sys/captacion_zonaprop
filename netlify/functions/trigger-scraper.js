exports.handler = async (event) => {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: "Method Not Allowed" };
  }

  const SECRET = process.env.TRIGGER_SECRET;
  const GH_TOKEN = process.env.GITHUB_PAT;

  // Validar secret
  let body;
  try { body = JSON.parse(event.body); } catch { body = {}; }
  if (!SECRET || body.secret !== SECRET) {
    return { statusCode: 401, body: JSON.stringify({ error: "No autorizado" }) };
  }

  // Disparar el workflow en GitHub
  const response = await fetch(
    "https://api.github.com/repos/byanani73-sys/captacion_zonaprop/actions/workflows/scraper_diario.yml/dispatches",
    {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${GH_TOKEN}`,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: "master" }),
    }
  );

  if (response.status === 204) {
    return {
      statusCode: 200,
      body: JSON.stringify({ ok: true, message: "Scraper iniciado" }),
    };
  } else {
    const text = await response.text();
    return {
      statusCode: 500,
      body: JSON.stringify({ error: "Error al disparar workflow", detail: text }),
    };
  }
};
