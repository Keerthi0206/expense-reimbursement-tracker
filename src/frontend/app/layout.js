import "./globals.css";
import { AuthProvider } from "../lib/auth-context";
import { ThemeProvider } from "../lib/theme-context";

export const metadata = {
  title: "CDF Expense & Reimbursement Tracker",
  description: "Submit and review reimbursement requests",
};

// Runs before React hydrates so the page never flashes the wrong theme:
// reads the saved preference (or system preference) and sets the attribute
// on <html> synchronously, before first paint.
const themeInitScript = `
(function () {
  try {
    var saved = localStorage.getItem("cdf_theme");
    var theme = saved || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.setAttribute("data-theme", theme);
  } catch (e) {}
})();
`;

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <ThemeProvider>
          <AuthProvider>{children}</AuthProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
