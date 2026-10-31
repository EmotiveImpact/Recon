// Ready-made kinds of business to add to a target list in one click.
// Overture names are checked against Overture's own list (see categories.json);
// OpenStreetMap tags follow the OSM wiki; SIC codes are the UK's 2007 trade codes.
import type { Sector } from "./api";

export type Preset = { name: string; emoji: string; hint: string; sector: Sector };

const preset = (name: string, emoji: string, hint: string, overture: string[], osm: [string, string][], sic: string[]): Preset => ({
  name, emoji, hint, sector: { overture, osm, sic },
});

export const LIBRARY: Preset[] = [
  preset("Hair and beauty", "💇", "Hairdressers, beauty and nail salons", ["hair_salon", "beauty_salon", "nail_salon", "eyelash_service", "waxing", "hair_removal", "skin_care_and_makeup", "tanning_salon", "makeup_artist", "personal_or_beauty_service"], [["shop", "hairdresser"], ["shop", "beauty"]], ["96020"]),
  preset("Barbers", "💈", "Barber shops", ["barber"], [["hairdresser", "barber"]], ["96020"]),
  preset("Spas and massage", "🧖", "Spas, saunas and massage", ["spa", "day_spa", "health_spa", "massage_therapy", "sauna"], [["shop", "massage"], ["leisure", "sauna"], ["amenity", "spa"]], ["96040"]),
  preset("Tattoo and piercing", "🖋️", "Tattoo and piercing studios", ["tattoo", "tattoo_and_piercing", "piercing"], [["shop", "tattoo"], ["shop", "piercing"]], ["96090"]),
  preset("Aesthetics clinics", "💉", "Med spas, laser and skin clinics", ["medical_spa", "laser_hair_removal", "aesthetic_medicine"], [], ["86900"]),
  preset("Physio, chiro and osteo", "🦴", "Hands-on health clinics", ["physical_therapy", "chiropractic", "osteopathic_medicine", "sports_medicine"], [["healthcare", "physiotherapist"], ["healthcare", "chiropractor"], ["healthcare", "osteopath"]], ["86900"]),
  preset("Dentists", "🦷", "Dental practices", ["dental_clinic", "general_dentistry", "cosmetic_dentistry", "orthodontics", "pediatric_dentistry"], [["amenity", "dentist"], ["healthcare", "dentist"]], ["86230"]),
  preset("Opticians", "👓", "Opticians and optometrists", ["optometry", "eyewear_store", "vision_or_eye_care_clinic"], [["shop", "optician"]], ["47782", "86900"]),
  preset("Vets", "🐾", "Veterinary practices", ["veterinarian", "animal_hospital"], [["amenity", "veterinary"]], ["75000"]),
  preset("Pet grooming", "🐩", "Dog and pet groomers", ["pet_groomer"], [["shop", "pet_grooming"]], ["96090"]),
  preset("Gyms", "🏋️", "Gyms and fitness centres", ["gym", "sport_or_fitness_facility"], [["leisure", "fitness_centre"]], ["93130"]),
  preset("Yoga and Pilates", "🧘", "Yoga and Pilates studios", ["yoga_studio", "pilates_studio"], [["sport", "yoga"], ["sport", "pilates"]], ["93130", "85510"]),
  preset("Personal trainers", "🤸", "Personal trainers and boot camps", ["fitness_trainer", "boot_camp"], [], ["93130"]),
  preset("Martial arts and dance", "🥋", "Martial arts and dance schools", ["martial_arts_club", "dance_studio"], [["sport", "martial_arts"], ["leisure", "dance"]], ["85510", "85520"]),
  preset("Cafés", "☕", "Cafés and coffee shops", ["cafe", "coffee_shop"], [["amenity", "cafe"]], ["56102", "56103"]),
  preset("Restaurants", "🍽️", "Restaurants", ["restaurant"], [["amenity", "restaurant"]], ["56101"]),
  preset("Pubs and bars", "🍺", "Pubs and bars", ["pub", "bar", "cocktail_bar", "wine_bar"], [["amenity", "pub"], ["amenity", "bar"]], ["56302"]),
  preset("Bakeries", "🥐", "Bakeries and cake shops", ["bakery", "patisserie_cake_shop"], [["shop", "bakery"]], ["10710", "47240"]),
  preset("Florists", "💐", "Florists", ["florist", "flowers_and_gifts_store"], [["shop", "florist"]], ["47760"]),
  preset("Photographers", "📷", "Photographers and studios", ["photography_service", "event_photography_service", "session_photography_service"], [["craft", "photographer"], ["shop", "photo"]], ["74201", "74202", "74209"]),
  preset("Wedding services", "💍", "Bridal shops and planners", ["bridal_shop", "wedding_planning"], [["shop", "wedding"]], []),
  preset("Accountants", "📊", "Accountants and bookkeepers", ["accountant", "bookkeeper", "tax_service"], [["office", "accountant"], ["office", "tax_advisor"]], ["69201", "69202", "69203"]),
  preset("Solicitors", "⚖️", "Law firms and solicitors", ["attorney_or_law_firm", "legal_service"], [["office", "lawyer"]], ["69102"]),
  preset("Estate agents", "🏠", "Estate and letting agents", ["real_estate_agent", "real_estate_service", "property_management"], [["office", "estate_agent"]], ["68310"]),
  preset("Builders and trades", "🛠️", "Builders, plumbers, electricians", ["contractor", "plumbing", "electrician", "roofing", "carpenter", "painting"], [["craft", "plumber"], ["craft", "electrician"], ["craft", "builder"]], ["43210", "43220", "41202"]),
  preset("Garages", "🚗", "Car repair and MOT", ["automotive_repair", "auto_body_shop", "tire_shop"], [["shop", "car_repair"]], ["45200"]),
  preset("Cleaners", "🧽", "Cleaning companies", ["cleaning_service", "home_cleaning", "office_cleaning", "carpet_cleaning"], [], ["81210", "81229"]),
  preset("Nurseries and childcare", "🧸", "Nurseries and childminders", ["child_care_and_day_care", "preschool", "day_care_preschool"], [["amenity", "kindergarten"], ["amenity", "childcare"]], ["88910", "85100"]),
  preset("Tutors and schools", "📚", "Tutoring and private lessons", ["tutoring_service", "private_tutor", "music_school", "language_school", "driving_school"], [["amenity", "driving_school"], ["amenity", "music_school"]], ["85590", "85530"]),
  preset("Clothing boutiques", "👗", "Independent clothes shops", ["clothing_store", "womens_clothing_store", "fashion_boutique", "mens_clothing_store"], [["shop", "clothes"], ["shop", "boutique"]], ["47710"]),
  preset("Hotels and B&Bs", "🛏️", "Hotels, guest houses and B&Bs", ["hotel", "bed_and_breakfast", "guest_house", "inn"], [["tourism", "hotel"], ["tourism", "guest_house"]], ["55100", "55201"]),
];
