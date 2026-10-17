// fonts ship with the app (no web fonts: Google Fonts is unreachable in China)
import "@fontsource-variable/inter/wght.css";
import "@fontsource-variable/jetbrains-mono/wght.css";
import "misans/lib/Normal/MiSansVF.min.css";
import "./styles.css"; // first: feature styles (imported by the features) come after it
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
