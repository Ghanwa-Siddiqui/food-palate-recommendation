// ==========================================
// 1. TYPES & CONTRACT INTERFACES
// ==========================================

export interface Dish {
  id: string;
  name: string;
  restaurantId: string;
  restaurantName: string;
  price: number;
  dietaryTags: string[];
  dishVector: number[];
  lat: number | null;
  lng: number | null;
  locationVerified: boolean; // From Data Core boundary rule
  popularityScore: number; // 0-100
  imageUrl?: string;
}

export interface UserTasteProfile {
  userId: string;
  tasteVector: number[];
  budgetMax: number;
  dietaryRestrictions: string[];
  userLat: number;
  userLng: number;
  maxDistanceKm: number;
}

export interface ReviewSummary {
  dishId: string;
  reviewScore: number; // 0 - 100
  avgSentiment: number;
  topAspects: string[];
}

export interface InteractionPayload {
  userId: string;
  dishId: string;
  interactionType: 'click' | 'save' | 'order';
  timestamp: string;
}

// ==========================================
// 2. DAY 2: MATH & DISTANCE UTILITIES
// ==========================================

/**
 * Day 2: Calculates distance using Haversine formula (in km)
 */
export function calculateHaversineDistance(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number {
  const R = 6371; // Earth's radius in km
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

/**
 * Calculates cosine similarity between vector embeddings.
 */
export function calculateCosineSimilarity(vecA: number[], vecB: number[]): number {
  if (!vecA || !vecB || vecA.length !== vecB.length) return 0;
  let dotProduct = 0, normA = 0, normB = 0;
  for (let i = 0; i < vecA.length; i++) {
    dotProduct += vecA[i] * vecB[i];
    normA += vecA[i] * vecA[i];
    normB += vecB[i] * vecB[i];
  }
  return normA === 0 || normB === 0 ? 0 : dotProduct / (Math.sqrt(normA) * Math.sqrt(normB));
}

// ==========================================
// 3. DAY 1 & DAY 2: CANDIDATE FILTERING & SCORING PIPELINE
// ==========================================

/**
 * Day 1 Candidate Generator: Filters dishes by budget, diet, & verified location distance.
 */
export function filterCandidates(dishes: Dish[], user: UserTasteProfile): Dish[] {
  return dishes.filter((dish) => {
    // 1. Budget Filter
    if (dish.price > user.budgetMax) return false;

    // 2. Dietary Filter
    const meetsDietary = user.dietaryRestrictions.every((restriction) =>
      dish.dietaryTags.includes(restriction)
    );
    if (!meetsDietary) return false;

    // 3. Location Filter (Respecting Data Core's location_verified flag)
    if (dish.locationVerified && dish.lat !== null && dish.lng !== null) {
      const distance = calculateHaversineDistance(user.userLat, user.userLng, dish.lat, dish.lng);
      if (distance > user.maxDistanceKm) return false;
    }

    return true;
  });
}

/**
 * Day 1 Weighted Scoring Formula:
 * Taste 45 / Food 20 / Reviews 10 / Distance 10 / Price 10 / Popularity 5
 */
export function calculateCompositeScore(
  dish: Dish,
  user: UserTasteProfile,
  reviewSummary?: ReviewSummary
): { totalScore: number; matchPercentage: number; distanceKm: number | null } {
  // 1. Taste Alignment (45%)
  const tasteSim = calculateCosineSimilarity(user.tasteVector, dish.dishVector);
  const tasteScore = Math.max(0, tasteSim) * 100;

  // 2. Food Vector Match (20%)
  const foodVectorScore = tasteScore;

  // 3. Review Intelligence Score (10%)
  const reviewScore = reviewSummary ? reviewSummary.reviewScore : 70;

  // 4. Distance Score (10%) & Haversine Calc
  let distanceKm: number | null = null;
  let distanceScore = 50; // default score if unverified

  if (dish.locationVerified && dish.lat !== null && dish.lng !== null) {
    distanceKm = calculateHaversineDistance(user.userLat, user.userLng, dish.lat, dish.lng);
    distanceScore = Math.max(0, 100 * (1 - distanceKm / Math.max(user.maxDistanceKm, 1)));
  }

  // 5. Price Normalization Score (10%)
  const priceScore = Math.max(0, 100 * (1 - dish.price / user.budgetMax));

  // 6. Popularity Score (5%)
  const popularityScore = dish.popularityScore;

  // Composite Formula
  const totalScore =
    0.45 * tasteScore +
    0.20 * foodVectorScore +
    0.10 * reviewScore +
    0.10 * distanceScore +
    0.10 * priceScore +
    0.05 * popularityScore;

  return {
    totalScore,
    matchPercentage: Math.min(99, Math.round(totalScore)),
    distanceKm: distanceKm ? parseFloat(distanceKm.toFixed(1)) : null,
  };
}

// ==========================================
// 4. CONTRACT MOCKS & API SWAP SERVICE
// ==========================================

export class TasteEngineService {
  private useRealApi: boolean;

  constructor(useRealApi = false) {
    this.useRealApi = useRealApi;
  }

  async getDishes(): Promise<Dish[]> {
    if (this.useRealApi) {
      const res = await fetch('/api/dishes');
      return res.json();
    }
    // Day 1 Mock Data (Ganva's Data Core Contract)
    return [
      {
        id: 'd1',
        name: 'Beef Nihari',
        restaurantId: 'r1',
        restaurantName: 'Waris Nihari',
        price: 650,
        dietaryTags: ['halal'],
        dishVector: [0.9, 0.85, 0.1, 0.95, 0.4],
        lat: 31.5721,
        lng: 74.3125,
        locationVerified: true,
        popularityScore: 95,
        imageUrl: 'https://foodish-api.com/images/butter-chicken/butter-chicken1.jpg',
      },
      {
        id: 'd2',
        name: 'Chicken Karahi',
        restaurantId: 'r2',
        restaurantName: 'Butt Karahi',
        price: 1200,
        dietaryTags: ['halal'],
        dishVector: [0.85, 0.9, 0.2, 0.7, 0.5],
        lat: 31.5315,
        lng: 74.357,
        locationVerified: true,
        popularityScore: 92,
        imageUrl: 'https://foodish-api.com/images/butter-chicken/butter-chicken8.jpg',
      },
    ];
  }

  async getUserProfile(userId: string): Promise<UserTasteProfile> {
    if (this.useRealApi) {
      const res = await fetch(`/api/user/${userId}/taste-vector`);
      return res.json();
    }
    // Day 1 Mock Data (Manahil's Personalization Contract)
    return {
      userId,
      tasteVector: [0.92, 0.88, 0.15, 0.9, 0.35],
      budgetMax: 1500,
      dietaryRestrictions: ['halal'],
      userLat: 31.56,
      userLng: 74.32,
      maxDistanceKm: 10,
    };
  }

  async getReviewSummaries(): Promise<Record<string, ReviewSummary>> {
    if (this.useRealApi) {
      const res = await fetch('/api/reviews/summaries');
      return res.json();
    }
    // Day 1 Mock Data (Ifreen's Review Intelligence Contract)
    return {
      d1: { dishId: 'd1', reviewScore: 96, avgSentiment: 0.9, topAspects: ['Very spicy', 'Slow-cooked'] },
      d2: { dishId: 'd2', reviewScore: 91, avgSentiment: 0.85, topAspects: ['Rich gravy'] },
    };
  }

  async logInteraction(payload: InteractionPayload): Promise<void> {
    if (this.useRealApi) {
      await fetch(`/api/user/${payload.userId}/interaction`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    } else {
      console.log('[Interaction Logged]:', payload);
    }
  }
}