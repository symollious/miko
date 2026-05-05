export const metadata = {
  title: 'Miko - Real-Time AI',
  description: 'Real-time AI companion',
};

export const viewport = {
  width: 'device-width',
  initialScale: 1,
};

import './globals.css';

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
