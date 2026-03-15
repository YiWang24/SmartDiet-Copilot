const ENERGY_FLOORS = {
  male: 1500,
  female: 1200,
};

const EER_EQUATIONS = {
  male: {
    sedentary: ({ age, heightCm, weightKg }) => 753.07 - 10.83 * age + 6.5 * heightCm + 14.1 * weightKg,
    light: ({ age, heightCm, weightKg }) => 581.47 - 10.83 * age + 8.3 * heightCm + 14.94 * weightKg,
    moderate: ({ age, heightCm, weightKg }) => 1004.82 - 10.83 * age + 6.52 * heightCm + 15.91 * weightKg,
    very_active: ({ age, heightCm, weightKg }) => -517.88 - 10.83 * age + 15.61 * heightCm + 19.11 * weightKg,
  },
  female: {
    sedentary: ({ age, heightCm, weightKg }) => 584.9 - 7.01 * age + 5.72 * heightCm + 11.71 * weightKg,
    light: ({ age, heightCm, weightKg }) => 575.77 - 7.01 * age + 6.6 * heightCm + 12.14 * weightKg,
    moderate: ({ age, heightCm, weightKg }) => 710.25 - 7.01 * age + 6.54 * heightCm + 12.34 * weightKg,
    very_active: ({ age, heightCm, weightKg }) => 511.83 - 7.01 * age + 9.07 * heightCm + 12.56 * weightKg,
  },
};

const GOAL_CALORIE_ADJUSTMENTS = {
  lose_weight: -500,
  gain_muscle: 250,
  maintenance: 0,
};

const PROTEIN_MULTIPLIERS = {
  lose_weight: 1.6,
  gain_muscle: 1.8,
  maintenance: 1.6,
};

const FAT_CALORIE_RATIOS = {
  lose_weight: 0.25,
  gain_muscle: 0.25,
  maintenance: 0.28,
};

function roundToInt(value) {
  return Math.round(Number(value) || 0);
}

function toPositiveNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function normalizeSex(value) {
  if (value === "male" || value === "female") return value;
  return null;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function getMissingTargetFields(input = {}) {
  const missing = [];
  if (!normalizeSex(input.biologicalSex)) missing.push("biologicalSex");
  if (!toPositiveNumber(input.age)) missing.push("age");
  if (!toPositiveNumber(input.heightCm)) missing.push("heightCm");
  if (!toPositiveNumber(input.weightKg)) missing.push("weightKg");
  return missing;
}

export function calculateMaintenanceCalories(input = {}) {
  const missingFields = getMissingTargetFields(input);
  if (missingFields.length) {
    return {
      ready: false,
      missingFields,
      maintenanceCalories: null,
    };
  }

  const biologicalSex = normalizeSex(input.biologicalSex);
  const age = Number(input.age);
  const heightCm = Number(input.heightCm);
  const weightKg = Number(input.weightKg);
  const activityLevel = input.activityLevel || "moderate";
  const equation = EER_EQUATIONS[biologicalSex][activityLevel] || EER_EQUATIONS[biologicalSex].moderate;
  const maintenanceCalories = equation({ age, heightCm, weightKg });

  return {
    ready: true,
    missingFields: [],
    maintenanceCalories: roundToInt(maintenanceCalories),
  };
}

export function calculateNutritionTargets(input = {}) {
  const maintenance = calculateMaintenanceCalories(input);
  if (!maintenance.ready) {
    return {
      ready: false,
      missingFields: maintenance.missingFields,
      maintenanceCalories: null,
      caloriesTarget: null,
      proteinGTarget: null,
      carbsGTarget: null,
      fatGTarget: null,
      calorieDelta: null,
    };
  }

  const biologicalSex = normalizeSex(input.biologicalSex);
  const goalType = GOAL_CALORIE_ADJUSTMENTS[input.goalType] ? input.goalType : "maintenance";
  const calorieDeltaRequested = GOAL_CALORIE_ADJUSTMENTS[goalType];
  const caloriesTarget = Math.max(
    ENERGY_FLOORS[biologicalSex],
    maintenance.maintenanceCalories + calorieDeltaRequested,
  );
  const calorieDelta = caloriesTarget - maintenance.maintenanceCalories;

  const weightKg = Number(input.weightKg);
  const proteinFloor = roundToInt(weightKg * PROTEIN_MULTIPLIERS[goalType]);
  const maxProtein = Math.floor((caloriesTarget * 0.35) / 4);
  const proteinGTarget = clamp(proteinFloor, 0, maxProtein);

  const desiredFatCalories = caloriesTarget * FAT_CALORIE_RATIOS[goalType];
  const minFat = Math.ceil((caloriesTarget * 0.2) / 9);
  const maxFat = Math.floor((caloriesTarget * 0.35) / 9);
  let fatGTarget = clamp(roundToInt(desiredFatCalories / 9), minFat, maxFat);
  let carbsGTarget = roundToInt((caloriesTarget - proteinGTarget * 4 - fatGTarget * 9) / 4);

  const minCarbs = Math.ceil((caloriesTarget * 0.45) / 4);
  if (carbsGTarget < minCarbs) {
    fatGTarget = Math.max(minFat, roundToInt((caloriesTarget - proteinGTarget * 4 - minCarbs * 4) / 9));
    carbsGTarget = roundToInt((caloriesTarget - proteinGTarget * 4 - fatGTarget * 9) / 4);
  }

  return {
    ready: true,
    missingFields: [],
    maintenanceCalories: maintenance.maintenanceCalories,
    caloriesTarget,
    proteinGTarget,
    carbsGTarget,
    fatGTarget,
    calorieDelta,
    methodology: "Health Canada DRI EER + AMDR-informed macro split",
  };
}

export function inferGoalType(goalTargets = {}, profile = {}) {
  const maintenance = calculateMaintenanceCalories(profile);
  if (!maintenance.ready || !goalTargets.caloriesTarget) return "maintenance";

  const delta = Number(goalTargets.caloriesTarget) - maintenance.maintenanceCalories;
  if (delta <= -250) return "lose_weight";
  if (delta >= 125) return "gain_muscle";
  return "maintenance";
}
