import React, { useState } from 'react';

export function Settings() {
  const [theme, setTheme] = useState('light');
  const [emailNotifications, setEmailNotifications] = useState(true);
  const [smsNotifications, setSmsNotifications] = useState(false);
  const [pushNotifications, setPushNotifications] = useState(true);

  return (
    <div className="max-w-4xl mx-auto">
      <h1 className="text-3xl font-bold mb-8">Settings</h1>

      <div className="space-y-8">
        {/* Appearance */}
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-xl font-bold mb-4">Appearance</h2>
          <p className="text-gray-600 mb-4">Customize how ShopHive looks on your device.</p>

          <div className="flex items-center justify-between py-4 border-b">
            <div>
              <p className="font-medium">Theme</p>
              <p className="text-sm text-gray-600">Switch between light and dark mode</p>
            </div>
            <div className="flex items-center space-x-3">
              <button
                data-ghost-id="theme.light"
                onClick={() => setTheme('light')}
                className={`px-4 py-2 rounded-lg border transition-colors ${
                  theme === 'light'
                    ? 'border-blue-600 bg-blue-50 text-blue-600'
                    : 'border-gray-300 hover:border-gray-400'
                }`}
              >
                ☀️ Light
              </button>
              <button
                data-ghost-id="theme.dark"
                onClick={() => setTheme('dark')}
                className={`px-4 py-2 rounded-lg border transition-colors ${
                  theme === 'dark'
                    ? 'border-blue-600 bg-blue-50 text-blue-600'
                    : 'border-gray-300 hover:border-gray-400'
                }`}
              >
                🌙 Dark
              </button>
            </div>
          </div>
        </section>

        {/* Notifications */}
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-xl font-bold mb-4">Notifications</h2>
          <p className="text-gray-600 mb-4">Manage how you receive notifications.</p>

          <div className="space-y-4">
            <div className="flex items-center justify-between py-4 border-b">
              <div>
                <p className="font-medium">Email Notifications</p>
                <p className="text-sm text-gray-600">Receive order updates and promotions via email</p>
              </div>
              <button
                data-ghost-id="settings.email_notifications"
                onClick={() => setEmailNotifications(!emailNotifications)}
                className={`relative w-14 h-8 rounded-full transition-colors ${
                  emailNotifications ? 'bg-blue-600' : 'bg-gray-300'
                }`}
              >
                <span
                  className={`absolute top-1 w-6 h-6 bg-white rounded-full shadow transition-transform ${
                    emailNotifications ? 'translate-x-7' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            <div className="flex items-center justify-between py-4 border-b">
              <div>
                <p className="font-medium">SMS Notifications</p>
                <p className="text-sm text-gray-600">Get text messages for shipping updates</p>
              </div>
              <button
                data-ghost-id="settings.sms_notifications"
                onClick={() => setSmsNotifications(!smsNotifications)}
                className={`relative w-14 h-8 rounded-full transition-colors ${
                  smsNotifications ? 'bg-blue-600' : 'bg-gray-300'
                }`}
              >
                <span
                  className={`absolute top-1 w-6 h-6 bg-white rounded-full shadow transition-transform ${
                    smsNotifications ? 'translate-x-7' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>

            <div className="flex items-center justify-between py-4">
              <div>
                <p className="font-medium">Push Notifications</p>
                <p className="text-sm text-gray-600">Enable browser push notifications</p>
              </div>
              <button
                data-ghost-id="settings.push_notifications"
                onClick={() => setPushNotifications(!pushNotifications)}
                className={`relative w-14 h-8 rounded-full transition-colors ${
                  pushNotifications ? 'bg-blue-600' : 'bg-gray-300'
                }`}
              >
                <span
                  className={`absolute top-1 w-6 h-6 bg-white rounded-full shadow transition-transform ${
                    pushNotifications ? 'translate-x-7' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>
          </div>
        </section>

        {/* Account */}
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-xl font-bold mb-4">Account</h2>

          <div className="space-y-4">
            <div className="flex items-center justify-between py-4 border-b">
              <div>
                <p className="font-medium">Email Address</p>
                <p className="text-sm text-gray-600">user@example.com</p>
              </div>
              <button className="text-blue-600 hover:underline text-sm font-medium">
                Change
              </button>
            </div>

            <div className="flex items-center justify-between py-4 border-b">
              <div>
                <p className="font-medium">Password</p>
                <p className="text-sm text-gray-600">Last changed 30 days ago</p>
              </div>
              <button className="text-blue-600 hover:underline text-sm font-medium">
                Update
              </button>
            </div>

            <div className="flex items-center justify-between py-4">
              <div>
                <p className="font-medium">Two-Factor Authentication</p>
                <p className="text-sm text-gray-600">Add an extra layer of security</p>
              </div>
              <button
                data-ghost-id="settings.2fa"
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700"
              >
                Enable
              </button>
            </div>
          </div>
        </section>

        {/* Saved Addresses */}
        <section className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold">Saved Addresses</h2>
            <button className="text-blue-600 hover:underline text-sm font-medium">
              + Add New
            </button>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between p-4 border rounded-lg">
              <div>
                <p className="font-medium">Home</p>
                <p data-ghost-id="settings.address.home" className="text-sm text-gray-600">
                  123 Main St, New York, NY 10001
                </p>
              </div>
              <button className="text-blue-600 hover:underline text-sm">Edit</button>
            </div>
            <div className="flex items-center justify-between p-4 border rounded-lg">
              <div>
                <p className="font-medium">Work</p>
                <p data-ghost-id="settings.address.work" className="text-sm text-gray-600">
                  456 Office Blvd, New York, NY 10002
                </p>
              </div>
              <button className="text-blue-600 hover:underline text-sm">Edit</button>
            </div>
          </div>
        </section>

        {/* Danger Zone */}
        <section className="bg-white rounded-xl border border-red-200 p-6">
          <h2 className="text-xl font-bold mb-4 text-red-600">Danger Zone</h2>

          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium">Delete Account</p>
              <p className="text-sm text-gray-600">
                Permanently delete your account and all data
              </p>
            </div>
            <button className="px-4 py-2 border border-red-600 text-red-600 rounded-lg text-sm font-medium hover:bg-red-50">
              Delete Account
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}