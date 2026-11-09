export type Page = "home" | "how" | "model" | "report";

export function siteHeader(page: Page, tagline: string): string {
  const current = (target: Page): string => (page === target ? ' aria-current="page"' : "");
  return `<header class="title-block">
      <h1><a href="#/">Does the Sheep Remember the Wolf?</a></h1>
      <nav class="site-nav" aria-label="Site">
        <a href="#/"${current("home")}>The field</a>
        <a href="#/#leaderboard">Leaderboard</a>
        <a href="#/report"${current("report")}>First run</a>
        <a href="#/how"${current("how")}>How it works</a>
      </nav>
      <p>${tagline}</p>
    </header>`;
}

export function siteFooter(): string {
  return `<footer class="site-foot">Open benchmark. Scores describe one model on one kind of task. Numbers come straight from the published run files.</footer>`;
}

export function errorState(message: string, hint: string): string {
  return `<div class="error-state" role="alert"><strong>${message}</strong><p>${hint}</p></div>`;
}
