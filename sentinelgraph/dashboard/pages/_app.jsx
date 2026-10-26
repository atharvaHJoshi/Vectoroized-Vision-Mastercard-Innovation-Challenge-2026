/**
 * Next.js custom App — the ONLY place globals.css may be imported.
 */
import "../styles/globals.css";

export default function MyApp({ Component, pageProps }) {
  return <Component {...pageProps} />;
}
