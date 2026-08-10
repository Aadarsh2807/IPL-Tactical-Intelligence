import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import SquadBuilder from './components/SquadBuilder';
import BowlingRecommender from './components/BowlingRecommender';
import SeasonOutlook from './components/SeasonOutlook';

function App() {
  const [activeTab, setActiveTab] = useState('squad');

  const tabs = [
    { id: 'squad', label: 'Squad Builder' },
    { id: 'matchup', label: 'Player Matchups' },
    { id: 'outlook', label: 'Season Outlook' },
  ];

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 font-sans relative overflow-hidden">
      {/* Background Gradient Animation */}
      <div className="absolute inset-0 z-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-indigo-900/30 via-slate-900 to-slate-900"></div>

      <div className="relative z-10 max-w-6xl mx-auto px-4 py-8">
        <header className="mb-12 text-center">
          <motion.h1 
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-4xl md:text-5xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-500 mb-4 tracking-tight"
          >
            IPL Tactical Decision Intelligence
          </motion.h1>
          <motion.p 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="text-slate-400 max-w-2xl mx-auto"
          >
            Data-backed insights for team composition, matchups, and live win probabilities.
          </motion.p>
        </header>

        {/* Navigation Tabs */}
        <div className="flex justify-center mb-12 space-x-2 md:space-x-4">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 md:px-6 md:py-3 rounded-full font-medium transition-all ${
                activeTab === tab.id 
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30' 
                  : 'bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-white'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Main Content Area */}
        <div className="bg-slate-800/50 backdrop-blur-xl border border-slate-700 rounded-3xl p-6 md:p-10 shadow-2xl min-h-[500px]">
          <AnimatePresence mode="wait">
            {activeTab === 'squad' && (
              <motion.div
                key="squad"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                transition={{ duration: 0.3 }}
              >
                <SquadBuilder />
              </motion.div>
            )}
            {activeTab === 'matchup' && (
              <motion.div
                key="matchup"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                transition={{ duration: 0.3 }}
              >
                <BowlingRecommender />
              </motion.div>
            )}
            {activeTab === 'outlook' && (
              <motion.div key="outlook" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }} transition={{ duration: 0.3 }}>
                <SeasonOutlook />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

export default App;
