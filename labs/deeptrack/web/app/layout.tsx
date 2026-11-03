import "@copilotkit/react-core/v2/styles.css";
import { Providers } from "./providers";

export const metadata = { title: "deeptrack · labs" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body style={{ margin: 0, height: "100vh" }}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
