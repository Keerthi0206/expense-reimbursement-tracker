import "./globals.css";
import { AuthProvider } from "../lib/auth-context";

export const metadata = {
  title: "CDF Expense & Reimbursement Tracker",
  description: "Submit and review reimbursement requests",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
