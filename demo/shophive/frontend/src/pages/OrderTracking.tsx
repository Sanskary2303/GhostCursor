import React from 'react';

const ORDERS = [
  {
    id: 'SH-1024',
    date: '2024-01-15',
    status: 'Shipped',
    items: [{ name: 'Nike Air Max 90', size: '10', price: 129.99 }],
    total: 129.99,
    tracking: '1Z999AA10123456784',
    carrier: 'UPS',
    timeline: [
      { status: 'Order Placed', date: 'Jan 15, 2024', completed: true },
      { status: 'Processing', date: 'Jan 16, 2024', completed: true },
      { status: 'Shipped', date: 'Jan 17, 2024', completed: true },
      { status: 'Out for Delivery', date: 'Jan 19, 2024', completed: false },
      { status: 'Delivered', date: 'Jan 20, 2024', completed: false },
    ],
  },
  {
    id: 'SH-987',
    date: '2024-01-10',
    status: 'Delivered',
    items: [{ name: 'Air Jordan 1 Retro', size: '10', price: 179.99 }],
    total: 179.99,
    tracking: '1Z999AA10123456780',
    carrier: 'FedEx',
    timeline: [
      { status: 'Order Placed', date: 'Jan 10, 2024', completed: true },
      { status: 'Processing', date: 'Jan 11, 2024', completed: true },
      { status: 'Shipped', date: 'Jan 12, 2024', completed: true },
      { status: 'Out for Delivery', date: 'Jan 14, 2024', completed: true },
      { status: 'Delivered', date: 'Jan 15, 2024', completed: true },
    ],
  },
];

export function OrderTracking() {
  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold mb-8">My Orders</h1>

      <div className="space-y-6">
        {ORDERS.map((order) => (
          <div
            key={order.id}
            data-ghost-id={`orders.order.${order.id}`}
            className="bg-white rounded-xl border border-gray-200 overflow-hidden"
          >
            {/* Order Header */}
            <div className="bg-gray-50 px-6 py-4 flex items-center justify-between">
              <div>
                <div className="flex items-center space-x-3">
                  <span data-ghost-id={`orders.${order.id}.id`} className="font-bold text-lg">
                    Order #{order.id}
                  </span>
                  <span
                    data-ghost-id={`orders.${order.id}.status`}
                    className={`px-3 py-1 rounded-full text-xs font-medium ${
                      order.status === 'Delivered'
                        ? 'bg-green-100 text-green-800'
                        : order.status === 'Shipped'
                        ? 'bg-blue-100 text-blue-800'
                        : 'bg-yellow-100 text-yellow-800'
                    }`}
                  >
                    {order.status}
                  </span>
                </div>
                <p className="text-sm text-gray-600 mt-1">Placed on {order.date}</p>
              </div>
              <button
                data-ghost-id={`orders.${order.id}.track`}
                className="text-blue-600 hover:underline text-sm font-medium"
              >
                Track Package →
              </button>
            </div>

            {/* Order Items */}
            <div className="p-6">
              <div className="space-y-4 mb-6">
                {order.items.map((item, idx) => (
                  <div key={idx} className="flex items-center space-x-4">
                    <div className="w-16 h-16 bg-gray-100 rounded-lg flex items-center justify-center text-2xl">
                      👟
                    </div>
                    <div>
                      <p className="font-medium">{item.name}</p>
                      <p className="text-sm text-gray-600">Size: US {item.size}</p>
                    </div>
                    <div className="ml-auto font-medium">${item.price}</div>
                  </div>
                ))}
              </div>

              {/* Tracking Timeline */}
              <div className="border-t pt-6">
                <h3 data-ghost-id={`orders.${order.id}.tracking`} className="font-semibold mb-4">
                  Tracking: {order.carrier} {order.tracking}
                </h3>
                <div className="flex items-center justify-between">
                  {order.timeline.map((step, idx) => (
                    <div key={idx} className="flex flex-col items-center flex-1 relative">
                      {/* Line connector */}
                      {idx > 0 && (
                        <div
                          className={`absolute top-4 -left-1/2 w-full h-0.5 ${
                            step.completed ? 'bg-blue-600' : 'bg-gray-200'
                          }`}
                        />
                      )}
                      <div
                        className={`w-8 h-8 rounded-full flex items-center justify-center z-10 ${
                          step.completed ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-400'
                        }`}
                      >
                        {step.completed ? '✓' : idx + 1}
                      </div>
                      <p
                        className={`mt-2 text-xs text-center ${
                          step.completed ? 'font-medium text-gray-900' : 'text-gray-500'
                        }`}
                      >
                        {step.status}
                      </p>
                      <p className="text-xs text-gray-400">{step.date}</p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Order Total */}
              <div className="border-t mt-6 pt-4 flex justify-between items-center">
                <span className="text-gray-600">Order Total</span>
                <span data-ghost-id={`orders.${order.id}.total`} className="text-xl font-bold">
                  ${order.total.toFixed(2)}
                </span>
              </div>
            </div>

            {/* Actions */}
            <div className="bg-gray-50 px-6 py-4 flex space-x-4">
              <button
                data-ghost-id={`orders.${order.id}.view_details`}
                className="text-blue-600 hover:underline text-sm font-medium"
              >
                View Details
              </button>
              <button
                data-ghost-id={`orders.${order.id}.download_receipt`}
                className="text-blue-600 hover:underline text-sm font-medium"
              >
                Download Receipt
              </button>
              <button
                data-ghost-id={`orders.${order.id}.return`}
                className="text-blue-600 hover:underline text-sm font-medium"
              >
                Start Return
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}