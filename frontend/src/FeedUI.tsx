import React, { useEffect, useState } from 'react';
import {
  TasteEngineService,
  Dish,
  filterCandidates,
  calculateCompositeScore,
} from './TasteEngineService';

export const FeedUI: React.FC<{ userId: string }> = ({ userId }) => {
  const [items, setItems] = useState<Array<{ dish: Dish; matchPercentage: number; distanceKm: number | null }>>([]);
  const [loading, setLoading] = useState(true);

  // Toggle true on Day 2 when backend APIs merge into develop
  const engineService = new TasteEngineService(false); 

  useEffect(() => {
    async function fetchFeed() {
      setLoading(true);
      const [allDishes, user, reviews] = await Promise.all([
        engineService.getDishes(),
        engineService.getUserProfile(userId),
        engineService.getReviewSummaries(),
      ]);

      const candidates = filterCandidates(allDishes, user);
      const scored = candidates.map((dish) => {
        const review = reviews[dish.id];
        const { matchPercentage, distanceKm } = calculateCompositeScore(dish, user, review);
        return { dish, matchPercentage, distanceKm };
      });

      scored.sort((a, b) => b.matchPercentage - a.matchPercentage);
      setItems(scored);
      setLoading(false);
    }

    fetchFeed();
  }, [userId]);

  const handleInteraction = (dishId: string, type: 'click' | 'save' | 'order') => {
    engineService.logInteraction({
      userId,
      dishId,
      interactionType: type,
      timestamp: new Date().toISOString(),
    });
  };

  if (loading) return <div style={{ padding: '24px', textAlign: 'center' }}>Loading your personalized feed...</div>;

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', padding: '16px' }}>
      <header style={{ marginBottom: '20px' }}>
        <h2 style={{ fontFamily: 'Georgia, serif', fontSize: '24px', margin: 0 }}>Recommended for You</h2>
        <p style={{ color: '#5A544A', fontSize: '14px', marginTop: '4px' }}>Ranked based on your taste vector & preferences</p>
      </header>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {items.map(({ dish, matchPercentage, distanceKm }) => (
          <div
            key={dish.id}
            onClick={() => handleInteraction(dish.id, 'click')}
            style={{
              border: '1px solid #E0D8C6',
              borderRadius: '12px',
              padding: '16px',
              backgroundColor: '#FBF7EE',
              display: 'flex',
              flexDirection: 'row', // Default flex row
              gap: '16px',
              cursor: 'pointer',
            }}
          >
            {dish.imageUrl && (
              <img
                src={dish.imageUrl}
                alt={dish.name}
                style={{ width: '110px', height: '110px', borderRadius: '8px', objectFit: 'cover' }}
              />
            )}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <h3 style={{ margin: 0, fontSize: '18px' }}>{dish.name}</h3>
                  <span style={{ backgroundColor: '#E8A93A', color: '#1C1917', fontWeight: 600, padding: '4px 10px', borderRadius: '20px', fontSize: '12px' }}>
                    {matchPercentage}% match
                  </span>
                </div>
                <p style={{ color: '#5A544A', fontSize: '13px', margin: '6px 0' }}>
                  {dish.restaurantName} • Rs. {dish.price} {distanceKm !== null ? `• ${distanceKm} km away` : ''}
                </p>
              </div>

              {/* Day 2 Action Buttons */}
              <div style={{ display: 'flex', gap: '10px', marginTop: '12px' }}>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleInteraction(dish.id, 'save');
                  }}
                  style={{ border: '1px solid #1C1917', background: 'transparent', padding: '6px 14px', borderRadius: '6px', cursor: 'pointer', fontSize: '13px' }}
                >
                  Save
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleInteraction(dish.id, 'order');
                  }}
                  style={{ border: 'none', background: '#E8A93A', color: '#1C1917', padding: '6px 14px', borderRadius: '6px', fontWeight: 500, cursor: 'pointer', fontSize: '13px' }}
                >
                  Order
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};