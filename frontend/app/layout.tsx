import type { Metadata } from 'next'
import { DM_Sans, DM_Serif_Display, DM_Mono } from 'next/font/google'
import './globals.css'
import { TabNav } from './TabNav'
import { PrivateModeProvider } from '@/context/PrivateModeContext'
import { DarkModeProvider } from '@/context/DarkModeContext'

const dmSans = DM_Sans({
  subsets: ['latin'],
  variable: '--font-dm-sans',
  display: 'swap',
})

const dmSerifDisplay = DM_Serif_Display({
  subsets: ['latin'],
  weight: '400',
  variable: '--font-dm-serif',
  display: 'swap',
})

const dmMono = DM_Mono({
  subsets: ['latin'],
  weight: ['300', '400', '500'],
  variable: '--font-dm-mono',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Portfolio Tracker',
  description: 'Personal investment portfolio tracker',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${dmSans.variable} ${dmSerifDisplay.variable} ${dmMono.variable}`}>
      <body className="font-sans bg-page text-primary min-h-screen">
        <DarkModeProvider>
          <PrivateModeProvider>
            <TabNav />
            <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
          </PrivateModeProvider>
        </DarkModeProvider>
      </body>
    </html>
  )
}
