import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { CartProvider } from './cart/CartContext';
import { ThemeProvider } from './theme/ThemeContext';
import { NavigationHeader } from './components/NavigationHeader';
import { CartToast } from './components/CartToast';
import { Home } from './pages/Home';
import { ProductDetail } from './pages/ProductDetail';
import { Cart } from './pages/Cart';
import { Checkout } from './pages/Checkout';
import { OrderTracking } from './pages/OrderTracking';
import { Settings } from './pages/Settings';

// [GHOST-CURSOR INTEGRATION]
import { GhostCursor } from '@ghost-cursor/sdk-react';

const ROUTE_PAGES: Record<string, string> = { '/': 'home', '/cart': 'cart', '/checkout': 'checkout', '/orders': 'orders', '/settings': 'settings' };

// [GHOST-CURSOR INTEGRATION]
const ghostContext = {
  page: () => (window.location.pathname.startsWith('/product/') ? 'products' : ROUTE_PAGES[window.location.pathname] ?? 'home'),
};
const ghostTheme = { primaryColor: '#3B7BDF', cursorColor: '#3B7BDF', mode: 'midnight' as const, position: 'bottom-right' as const };

export function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <CartProvider>
          <div className="min-h-screen bg-gray-50 text-gray-900">
            <NavigationHeader />
            <CartToast />

            <main className="container mx-auto px-4 py-8">
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/product/:id" element={<ProductDetail />} />
                <Route path="/cart" element={<Cart />} />
                <Route path="/checkout" element={<Checkout />} />
                <Route path="/orders" element={<OrderTracking />} />
                <Route path="/settings" element={<Settings />} />
              </Routes>
            </main>

            {/* [GHOST-CURSOR INTEGRATION] */}
            <GhostCursor
              apiEndpoint="/api/ghost-cursor"
              theme={ghostTheme}
              context={ghostContext}
              requireApprovalForActions={true}
            />
          </div>
        </CartProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}