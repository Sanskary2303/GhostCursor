import React, { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useCart } from '../cart/CartContext';

export function NavigationHeader() {
  const location = useLocation();
  const { count } = useCart();
  const [user, setUser] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/me')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.user) {
          setUser(data.user);
        }
      })
      .catch(() => {});
  }, []);

  const handleLogin = async () => {
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: 'demo' }),
      });
      if (res.ok) {
        const data = await res.json();
        setUser(data.user);
      }
    } catch {
      // ignore
    }
  };

  const handleLogout = async () => {
    try {
      const res = await fetch('/api/logout', { method: 'POST' });
      if (res.ok) {
        setUser(null);
      }
    } catch {
      // ignore
    }
  };

  const isActive = (path: string) => location.pathname === path;

  return (
    <header className="bg-white shadow-sm border-b border-gray-200">
      <div className="container mx-auto px-4">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <Link to="/" className="flex items-center space-x-2">
            <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-xl">S</span>
            </div>
            <span className="text-xl font-bold text-gray-900">ShopHive</span>
          </Link>

          {/* Navigation */}
          <nav className="hidden md:flex items-center space-x-8" data-ghost-id="nav">
            <Link
              to="/"
              data-ghost-id="nav.home"
              data-ghost-nav="/"
              className={`text-sm font-medium transition-colors ${
                isActive('/') ? 'text-blue-600' : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Home
            </Link>
            <Link
              to="/cart"
              data-ghost-id="nav.cart"
              data-ghost-nav="cart"
              aria-label={`Cart (${count})`}
              className={`text-sm font-medium transition-colors ${
                isActive('/cart') ? 'text-blue-600' : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Cart (<span key={count} className={count > 0 ? 'cart-bump' : ''}>{count}</span>)
            </Link>
            <Link
              to="/orders"
              data-ghost-id="nav.orders"
              data-ghost-nav="orders"
              className={`text-sm font-medium transition-colors ${
                isActive('/orders') ? 'text-blue-600' : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Orders
            </Link>
            <Link
              to="/settings"
              data-ghost-id="nav.settings"
              data-ghost-nav="settings"
              className={`text-sm font-medium transition-colors ${
                isActive('/settings') ? 'text-blue-600' : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              Settings
            </Link>
          </nav>

          {/* User auth and mobile menu */}
          <div className="flex items-center space-x-4">
            {user ? (
              <div className="flex items-center space-x-3 text-sm">
                <span className="text-gray-700 font-medium">Hi, {user}</span>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="text-gray-600 hover:text-gray-900 border border-gray-300 rounded px-2.5 py-1 text-xs font-medium hover:bg-gray-50 transition-colors"
                >
                  Sign out
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={handleLogin}
                className="bg-blue-600 hover:bg-blue-700 text-white rounded px-3 py-1.5 text-xs font-medium shadow-sm transition-colors"
              >
                Sign in (demo)
              </button>
            )}

            {/* Mobile menu button */}
            <button
              className="md:hidden p-2 rounded-lg hover:bg-gray-100"
              aria-label="Open menu"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}