import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { NavigationHeader } from './components/NavigationHeader';
import { Home } from './pages/Home';
import { ProductDetail } from './pages/ProductDetail';
import { Cart } from './pages/Cart';
import { Checkout } from './pages/Checkout';
import { OrderTracking } from './pages/OrderTracking';
import { Settings } from './pages/Settings';

// [GHOST-CURSOR INTEGRATION - STEP 1: IMPORT SDK COMPONENT]
import { GhostCursor } from '@ghost-cursor/sdk';

export function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50 text-gray-900">
        <NavigationHeader />

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

        {/* [GHOST-CURSOR INTEGRATION - STEP 2: MOUNT WIDGET WITH ENDPOINT & CONFIG] */}
        <GhostCursor
          apiEndpoint="/api/ghost-cursor"
          theme={{
            primaryColor: '#0052FF',
            cursorColor: '#FF4D4D',
            position: 'bottom-right',
          }}
          requireApprovalForActions={true}
        />
      </div>
    </BrowserRouter>
  );
}