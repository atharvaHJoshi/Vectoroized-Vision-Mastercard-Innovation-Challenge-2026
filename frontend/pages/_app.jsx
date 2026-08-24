/**
 * Next.js custom App.
 *
 * This is the ONLY place globals.css may be imported — Next.js rejects global
 * stylesheet imports from any other module.
 */
import "../styles/globals.css";

export default function MyApp({ Component, pageProps }) {
  return <Component {...pageProps} />;
}
