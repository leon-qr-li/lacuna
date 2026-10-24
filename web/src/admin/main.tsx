// The admin site (admin.<domain>, decision 2026-10-24-admin-site): its own page, fonts, styles and language.
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import "./admin.css";
import { createRoot } from "react-dom/client";
import { Admin, applyTheme } from "./Shell";

applyTheme();
createRoot(document.getElementById("root")!).render(<Admin />);
