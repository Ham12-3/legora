import { redirect } from 'next/navigation'

export default function Home() {
  // Middleware has already sent anonymous visitors to /login.
  redirect('/matters')
}
