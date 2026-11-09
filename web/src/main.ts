import "./styles.css";
import { renderHome, type PageView } from "./pages/home";
import { renderHow } from "./pages/how";
import { renderModel } from "./pages/model";
import { loadCanvasFonts } from "./theme";

const app = document.querySelector<HTMLElement>("#app")!;
const SHARED_MODEL_PATH = /^\/model\/([^/]+)\/?$/;
let current: PageView | null = null;
let onHome = false;

function destination(): string {
  const hash = window.location.hash.replace(/^#\/?/, "");
  if (hash) return hash;
  const shared = SHARED_MODEL_PATH.exec(window.location.pathname);
  return shared ? `model/${shared[1]}` : "";
}

function scrollToBoard(): void {
  document.querySelector("#leaderboard")?.scrollIntoView();
}

function route(): void {
  const target = destination();
  if (target === "#leaderboard" && onHome) {
    scrollToBoard();
    return;
  }
  current?.destroy();
  onHome = false;
  if (target === "how") {
    current = renderHow(app);
  } else if (target.startsWith("model/")) {
    current = renderModel(app, decodeURIComponent(target.slice("model/".length)));
  } else {
    current = renderHome(app);
    onHome = true;
  }
  window.scrollTo(0, 0);
  if (target === "#leaderboard") void current.ready?.then(scrollToBoard);
}

window.addEventListener("hashchange", route);
void loadCanvasFonts().finally(route);
