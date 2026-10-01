import "./globals.css";
export const metadata = { title: "CSV2Trust", description: "From Messy Spreadsheet to Trusted Data Pipeline." };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (<html lang="id"><body>{children}</body></html>);
}
